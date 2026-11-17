import hashlib
from datetime import datetime, timezone
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.database.base import Base
from app.database.connection import get_db
from app.database.models import Document, DocumentChunk, DocumentVersion
from app.database.models import IngestionJob
from app.main import app
from app.schemas.chunking import ChunkSource, DocumentChunkData
from app.schemas.extraction import ExtractionResult
from app.services.search.vector_indexing_service import IndexingSummary


def make_database():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return engine, sessionmaker(bind=engine, autoflush=False)


def test_upload_is_idempotent_and_status_is_queryable(tmp_path, monkeypatch):
    engine, session_factory = make_database()
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path / "uploads"))

    def override_get_db():
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as client:
            first = client.post(
                "/api/v1/documents",
                data={
                    "title": "Travel Policy",
                    "department": "People Operations",
                },
                files={
                    "file": (
                        "policy.txt",
                        b"Receipts are required for travel expenses.",
                        "text/plain",
                    )
                },
                headers={"Idempotency-Key": "upload-123"},
            )
            assert first.status_code == 202, first.text
            first_data = first.json()
            assert first_data["duplicate"] is False
            assert first_data["status"] == "queued"
            with session_factory() as session:
                jobs = session.query(IngestionJob).all()
                assert len(jobs) == 1
                assert jobs[0].status == "pending"
                assert jobs[0].source_path.endswith(".txt")

            duplicate = client.post(
                "/api/v1/documents",
                data={
                    "title": "Travel Policy",
                    "department": "People Operations",
                },
                files={
                    "file": (
                        "policy.txt",
                        b"Receipts are required for travel expenses.",
                        "text/plain",
                    )
                },
                headers={"Idempotency-Key": "upload-123"},
            )
            assert duplicate.status_code == 202, duplicate.text
            assert duplicate.json()["duplicate"] is True
            assert duplicate.json()["version_id"] == first_data["version_id"]
            with session_factory() as session:
                assert session.query(IngestionJob).count() == 1

            status_response = client.get(
                f"/api/v1/documents/{first_data['version_id']}"
            )
            assert status_response.status_code == 200
            assert status_response.json()["status"] == "queued"

            key_reuse = client.post(
                "/api/v1/documents",
                data={
                    "title": "Travel Policy",
                    "department": "People Operations",
                },
                files={
                    "file": (
                        "policy.txt",
                        b"Different content.",
                        "text/plain",
                    )
                },
                headers={"Idempotency-Key": "upload-123"},
            )
            assert key_reuse.status_code == 409

            with session_factory() as session:
                retry_version = session.get(
                    DocumentVersion,
                    UUID(first_data["version_id"]),
                )
                retry_version.status = "indexing_failed"
                retry_version.error_message = "temporary Azure error"
                retry_job = session.query(IngestionJob).filter_by(
                    version_id=retry_version.id
                ).one()
                retry_job.status = "dead_letter"
                retry_job.attempt_count = retry_job.max_attempts
                retry_job.last_error = "temporary Azure error"
                session.commit()

            retried = client.post(
                "/api/v1/documents",
                data={
                    "title": "Travel Policy",
                    "department": "People Operations",
                },
                files={
                    "file": (
                        "policy.txt",
                        b"Receipts are required for travel expenses.",
                        "text/plain",
                    )
                },
                headers={"Idempotency-Key": "upload-123"},
            )
            assert retried.status_code == 202
            assert retried.json()["duplicate"] is True
            with session_factory() as session:
                retry_job = session.query(IngestionJob).one()
                assert retry_job.status == "pending"
                assert retry_job.attempt_count == 0
                assert retry_job.last_error is None
    finally:
        app.dependency_overrides.pop(get_db, None)
        Base.metadata.drop_all(engine)
        engine.dispose()


def make_chunk():
    return DocumentChunkData(
        chunk_index=0,
        content="Travel expenses require receipts.",
        token_count=12,
        section_path="Travel",
        sources=[
            ChunkSource(
                page_number=1,
                block_index=1,
                char_start=0,
                char_end=33,
            )
        ],
        source_token_start=0,
        source_token_end=5,
        source_token_count=5,
    )


def seed_versions(session_factory):
    document_id = uuid4()
    old_version_id = uuid4()
    new_version_id = uuid4()
    with session_factory() as session:
        document = Document(
            id=document_id,
            title="Travel Policy",
            department="People Operations",
        )
        session.add(document)
        session.flush()
        old_version = DocumentVersion(
            id=old_version_id,
            document_id=document_id,
            version_number=1,
            filename="old.txt",
            content_hash=hashlib.sha256(b"old").hexdigest(),
            status="published",
            expected_chunks=1,
            indexed_chunks=1,
            published_at=datetime.now(timezone.utc),
        )
        new_version = DocumentVersion(
            id=new_version_id,
            document_id=document_id,
            version_number=2,
            filename="new.txt",
            content_hash=hashlib.sha256(b"new").hexdigest(),
            status="uploaded",
            expected_chunks=0,
            indexed_chunks=0,
        )
        session.add_all([old_version, new_version])
        session.flush()
        document.current_version_id = old_version_id
        session.commit()
    return document_id, old_version_id, new_version_id


class FakeChunker:
    def chunk_extraction(self, extraction):
        return [make_chunk()]


class FakeIndexer:
    def __init__(self, fail=False):
        self.fail = fail

    def ensure_index(self):
        pass

    def index_and_verify_chunks(self, **kwargs):
        if self.fail:
            raise RuntimeError("Azure indexing unavailable")
        return IndexingSummary(expected_count=1, indexed_count=1)


def make_extraction(status="completed", failed_pages=0):
    return ExtractionResult(
        filename="new.txt",
        file_type="txt",
        status=status,
        pages=[],
        total_pages=1,
        successful_pages=1,
        failed_pages=failed_pages,
        extraction_errors=["One page failed"] if failed_pages else [],
    )


def process_seeded_version(
    session_factory,
    version_id,
    extraction,
    indexer,
):
    from app.services.ingestion.pipeline_service import process_ingestion_version

    process_ingestion_version(
        version_id=version_id,
        upload_path="unused.txt",
        request_id="pipeline-test",
        session_factory=session_factory,
        extractor=lambda _: extraction,
        chunker_factory=FakeChunker,
        indexer_factory=lambda: indexer,
    )


def test_pipeline_publishes_new_version_only_after_index_verification(tmp_path):
    engine, session_factory = make_database()
    document_id, old_version_id, new_version_id = seed_versions(session_factory)
    try:
        process_seeded_version(
            session_factory,
            new_version_id,
            make_extraction(),
            FakeIndexer(),
        )
        with session_factory() as session:
            document = session.get(Document, document_id)
            new_version = session.get(DocumentVersion, new_version_id)
            assert document.current_version_id == new_version_id
            assert new_version.status == "published"
            assert new_version.expected_chunks == 1
            assert new_version.indexed_chunks == 1
            assert new_version.published_at is not None
            stored_chunk = session.query(DocumentChunk).filter_by(
                version_id=new_version_id
            ).one()
            assert stored_chunk.token_count == 12
            assert stored_chunk.source_token_start == 0
            assert stored_chunk.source_token_end == 5
            assert '"block_index":1' in stored_chunk.sources_json
            assert session.query(DocumentVersion).filter_by(
                id=old_version_id
            ).one().status == "published"
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()


def test_partial_extraction_keeps_chunks_but_does_not_publish(tmp_path):
    engine, session_factory = make_database()
    document_id, _, new_version_id = seed_versions(session_factory)
    try:
        process_seeded_version(
            session_factory,
            new_version_id,
            make_extraction("partially_extracted", failed_pages=1),
            FakeIndexer(),
        )
        with session_factory() as session:
            document = session.get(Document, document_id)
            version = session.get(DocumentVersion, new_version_id)
            assert document.current_version_id != new_version_id
            assert version.status == "partial_extraction"
            assert version.expected_chunks == 1
            assert version.indexed_chunks == 0
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()


def test_indexing_failure_preserves_previous_published_version():
    engine, session_factory = make_database()
    document_id, old_version_id, new_version_id = seed_versions(session_factory)
    try:
        process_seeded_version(
            session_factory,
            new_version_id,
            make_extraction(),
            FakeIndexer(fail=True),
        )
        with session_factory() as session:
            document = session.get(Document, document_id)
            version = session.get(DocumentVersion, new_version_id)
            old_version = session.get(DocumentVersion, old_version_id)
            assert document.current_version_id == old_version_id
            assert version.status == "indexing_failed"
            assert version.indexed_chunks == 0
            assert old_version.status == "published"
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()
