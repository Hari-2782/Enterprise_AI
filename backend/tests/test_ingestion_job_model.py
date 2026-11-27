from hashlib import sha256
import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database.base import Base
from app.database.models import Document, DocumentVersion, IngestionJob


def test_ingestion_job_persists_pending_outbox_state():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    try:
        with Session(engine) as session:
            document = Document(
                title="Policy",
                department="Operations",
            )
            session.add(document)
            session.flush()
            version = DocumentVersion(
                document_id=document.id,
                version_number=1,
                filename="policy.txt",
                content_hash=sha256(b"policy").hexdigest(),
                status="queued",
                expected_chunks=0,
                indexed_chunks=0,
            )
            session.add(version)
            session.flush()
            job = IngestionJob(
                version_id=version.id,
                source_path="data/uploads/policy.txt",
                request_id="req-123",
            )
            session.add(job)
            session.commit()

            session.refresh(job)
            assert job.status == "pending"
            assert job.attempt_count == 0
            assert job.max_attempts == 5
            assert job.available_at is not None
            assert job.version_id == version.id
            assert job.version.id == version.id
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()


def test_only_one_outbox_job_can_exist_per_version():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    try:
        with Session(engine) as session:
            document = Document(
                title="Policy",
                department="Operations",
            )
            session.add(document)
            session.flush()
            version = DocumentVersion(
                document_id=document.id,
                version_number=1,
                filename="policy.txt",
                content_hash=sha256(b"policy").hexdigest(),
                status="queued",
                expected_chunks=0,
                indexed_chunks=0,
            )
            session.add(version)
            session.flush()
            session.add_all([
                IngestionJob(
                    version_id=version.id,
                    source_path="first.txt",
                    request_id="req-1",
                ),
                IngestionJob(
                    version_id=version.id,
                    source_path="second.txt",
                    request_id="req-2",
                ),
            ])
            with pytest.raises(IntegrityError):
                session.commit()
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()


def test_outbox_rejects_invalid_attempt_counts_and_states():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    try:
        with Session(engine) as session:
            document = Document(
                title="Policy",
                department="Operations",
            )
            session.add(document)
            session.flush()
            version = DocumentVersion(
                document_id=document.id,
                version_number=1,
                filename="policy.txt",
                content_hash=sha256(b"policy").hexdigest(),
                status="queued",
                expected_chunks=0,
                indexed_chunks=0,
            )
            session.add(version)
            session.flush()
            session.add(
                IngestionJob(
                    version_id=version.id,
                    source_path="policy.txt",
                    request_id="req-3",
                    status="unknown",
                    attempt_count=-1,
                )
            )
            with pytest.raises(IntegrityError):
                session.commit()
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()
