from datetime import datetime, timedelta, timezone
from hashlib import sha256
from uuid import uuid4

from sqlalchemy import create_engine
from sqlalchemy import select
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.database.base import Base
from app.database.models import Document, DocumentVersion, IngestionJob
from app.schemas.chunking import ChunkSource, DocumentChunkData
from app.schemas.extraction import ExtractionResult
from app.services.ingestion.pipeline_service import process_ingestion_version
from app.services.search.vector_indexing_service import IndexingSummary
from app.workers.ingestion_worker import (
    IngestionWorker,
    claim_next_job,
    finalize_job,
    renew_job_lease,
)


def make_database():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return engine, sessionmaker(bind=engine, autoflush=False)


def seed_job(session_factory, status="pending", attempt_count=0):
    document_id = uuid4()
    version_id = uuid4()
    job_id = uuid4()
    with session_factory() as session:
        document = Document(
            id=document_id,
            title="Worker Test",
            department="Engineering",
        )
        session.add(document)
        session.flush()
        version = DocumentVersion(
            id=version_id,
            document_id=document_id,
            version_number=1,
            filename="worker.txt",
            content_hash=sha256(b"worker").hexdigest(),
            status="queued",
            expected_chunks=0,
            indexed_chunks=0,
        )
        session.add(version)
        session.flush()
        job = IngestionJob(
            id=job_id,
            version_id=version_id,
            source_path="/uploads/worker.txt",
            request_id="worker-request",
            status=status,
            attempt_count=attempt_count,
        )
        session.add(job)
        session.commit()
    return document_id, version_id, job_id


def test_claim_is_atomic_and_retry_safe():
    engine, session_factory = make_database()
    try:
        _, version_id, job_id = seed_job(session_factory)
        claim = claim_next_job(session_factory, worker_id="worker-a")

        assert claim is not None
        assert claim.id == job_id
        assert claim.version_id == version_id
        assert claim.attempt_count == 1
        assert claim.lease_token is not None
        assert claim_next_job(session_factory, worker_id="worker-b") is None

        with session_factory() as session:
            job = session.get(IngestionJob, job_id)
            assert job.status == "processing"
            assert job.locked_by == "worker-a"
            assert job.lease_token == claim.lease_token
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()


def test_claim_query_uses_postgresql_skip_locked():
    statement = (
        select(IngestionJob)
        .where(IngestionJob.status == "pending")
        .with_for_update(skip_locked=True)
    )
    sql = str(statement.compile(dialect=postgresql.dialect()))
    assert "FOR UPDATE SKIP LOCKED" in sql


def test_expired_lease_is_reclaimed_with_a_new_fencing_token():
    engine, session_factory = make_database()
    try:
        _, _, job_id = seed_job(session_factory, status="processing", attempt_count=1)
        old_token = uuid4()
        with session_factory() as session:
            job = session.get(IngestionJob, job_id)
            job.locked_by = "crashed-worker"
            job.lease_token = old_token
            job.locked_at = datetime.now(timezone.utc) - timedelta(minutes=5)
            session.commit()

        claim = claim_next_job(
            session_factory,
            worker_id="recovery-worker",
            lease_seconds=30,
        )
        assert claim is not None
        assert claim.lease_token != old_token
        assert claim.attempt_count == 2
        assert claim_next_job(
            session_factory,
            worker_id="other-worker",
            lease_seconds=30,
        ) is None
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()


def test_renewal_and_finalization_reject_stale_lease_token():
    engine, session_factory = make_database()
    try:
        _, _, _ = seed_job(session_factory)
        claim = claim_next_job(session_factory, worker_id="worker-a")
        assert claim is not None
        assert renew_job_lease(
            claim.id,
            claim.lease_token,
            "worker-a",
            session_factory,
        )
        assert not renew_job_lease(
            claim.id,
            uuid4(),
            "worker-a",
            session_factory,
        )

        # Simulate the claim being replaced after lease expiry.
        with session_factory() as session:
            job = session.get(IngestionJob, claim.id)
            job.lease_token = uuid4()
            job.locked_by = "worker-b"
            session.commit()
        assert not finalize_job(
            claim,
            worker_id="worker-a",
            outcome="published",
            session_factory=session_factory,
        )
        with session_factory() as session:
            job = session.get(IngestionJob, claim.id)
            assert job.status == "processing"
            assert job.locked_by == "worker-b"
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()


def test_retry_backoff_then_dead_letter_preserves_publication_pointer():
    engine, session_factory = make_database()
    try:
        document_id, version_id, job_id = seed_job(
            session_factory,
            attempt_count=0,
        )
        with session_factory() as session:
            job = session.get(IngestionJob, job_id)
            job.max_attempts = 2
            session.commit()

        first = claim_next_job(session_factory, worker_id="worker-a")
        assert first is not None
        assert finalize_job(
            first,
            worker_id="worker-a",
            outcome="indexing_failed",
            session_factory=session_factory,
            retry_base_seconds=0,
            error_message="temporary error",
        )
        with session_factory() as session:
            job = session.get(IngestionJob, job_id)
            version = session.get(DocumentVersion, version_id)
            assert job.status == "pending"
            assert job.attempt_count == 1
            assert job.last_error == "temporary error"
            assert version.status == "retrying"

        second = claim_next_job(session_factory, worker_id="worker-a")
        assert second is not None
        assert finalize_job(
            second,
            worker_id="worker-a",
            outcome="indexing_failed",
            session_factory=session_factory,
            error_message="permanent error",
        )
        with session_factory() as session:
            job = session.get(IngestionJob, job_id)
            version = session.get(DocumentVersion, version_id)
            document = session.get(Document, document_id)
            assert job.status == "dead_letter"
            assert job.last_error == "permanent error"
            assert version.status == "worker_failed"
            assert document.current_version_id is None
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()


def test_worker_processes_claim_and_marks_success_complete():
    engine, session_factory = make_database()
    try:
        document_id, version_id, job_id = seed_job(session_factory)

        def fake_processor(**kwargs):
            assert kwargs["job_id"] == job_id
            assert kwargs["lease_token"] is not None
            with session_factory() as session:
                version = session.get(DocumentVersion, version_id)
                document = session.get(Document, document_id)
                version.status = "published"
                document.current_version_id = version_id
                session.commit()
            return "published"

        worker = IngestionWorker(
            session_factory=session_factory,
            processor=fake_processor,
            worker_id="test-worker",
            lease_seconds=30,
        )
        assert worker.run_once()
        with session_factory() as session:
            job = session.get(IngestionJob, job_id)
            version = session.get(DocumentVersion, version_id)
            document = session.get(Document, document_id)
            assert job.status == "completed"
            assert job.lease_token is None
            assert version.status == "published"
            assert document.current_version_id == version_id
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()


def test_pipeline_refuses_publish_when_worker_lease_is_stale():
    engine, session_factory = make_database()
    try:
        _, version_id, job_id = seed_job(session_factory)
        claim = claim_next_job(session_factory, worker_id="worker-a")
        assert claim is not None
        with session_factory() as session:
            job = session.get(IngestionJob, job_id)
            job.lease_token = uuid4()
            job.locked_by = "worker-b"
            session.commit()

        outcome = process_ingestion_version(
            version_id=version_id,
            upload_path="not-read.txt",
            request_id="stale-test",
            session_factory=session_factory,
            extractor=lambda _: (_ for _ in ()).throw(
                AssertionError("stale claim must be rejected before extraction")
            ),
            job_id=job_id,
            lease_token=claim.lease_token,
        )
        assert outcome == "stale"
        with session_factory() as session:
            version = session.get(DocumentVersion, version_id)
            assert version.status == "queued"
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()


def test_worker_that_loses_lease_during_indexing_cannot_publish():
    engine, session_factory = make_database()
    try:
        document_id, version_id, job_id = seed_job(session_factory)
        claim = claim_next_job(session_factory, worker_id="worker-a")
        assert claim is not None

        extraction = ExtractionResult(
            filename="worker.txt",
            file_type="txt",
            status="completed",
            pages=[],
            total_pages=1,
            successful_pages=1,
            failed_pages=0,
        )
        chunk = DocumentChunkData(
            chunk_index=0,
            content="Verified worker content.",
            token_count=12,
            section_path=None,
            sources=[
                ChunkSource(
                    page_number=1,
                    block_index=0,
                    char_start=0,
                    char_end=24,
                )
            ],
            source_token_start=0,
            source_token_end=4,
            source_token_count=4,
        )

        class OneChunker:
            def chunk_extraction(self, _extraction):
                return [chunk]

        class LeaseReplacingIndexer:
            def ensure_index(self):
                pass

            def index_and_verify_chunks(self, **_kwargs):
                with session_factory() as session:
                    job = session.get(IngestionJob, job_id)
                    job.lease_token = uuid4()
                    job.locked_by = "worker-b"
                    session.commit()
                return IndexingSummary(expected_count=1, indexed_count=1)

        outcome = process_ingestion_version(
            version_id=version_id,
            upload_path="not-read.txt",
            request_id="lease-fence-test",
            session_factory=session_factory,
            extractor=lambda _: extraction,
            chunker_factory=OneChunker,
            indexer_factory=LeaseReplacingIndexer,
            job_id=job_id,
            lease_token=claim.lease_token,
        )

        assert outcome == "stale"
        with session_factory() as session:
            version = session.get(DocumentVersion, version_id)
            document = session.get(Document, document_id)
            job = session.get(IngestionJob, job_id)
            assert version.status == "indexing"
            assert document.current_version_id is None
            assert job.locked_by == "worker-b"
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()
