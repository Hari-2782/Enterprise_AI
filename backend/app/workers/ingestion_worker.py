import logging
import os
import socket
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import and_, or_, select, update
from sqlalchemy.orm import Session

from app.core.loggin import configure_logging
from app.database.connection import SessionLocal
from app.database.models import DocumentVersion, IngestionJob
from app.services.ingestion.pipeline_service import process_ingestion_version


logger = logging.getLogger("enterprise-ai.worker")


@dataclass(frozen=True)
class ClaimedJob:
    id: UUID
    version_id: UUID
    source_path: str
    request_id: str
    lease_token: UUID
    attempt_count: int
    max_attempts: int


def claim_next_job(
    session_factory=SessionLocal,
    worker_id: str = "ingestion-worker",
    lease_seconds: float = 300,
) -> ClaimedJob | None:
    """Atomically claim one ready or lease-expired job using SKIP LOCKED."""
    now = datetime.now(timezone.utc)
    expired_before = now - timedelta(seconds=lease_seconds)
    ready_condition = and_(
        IngestionJob.status == "pending",
        IngestionJob.available_at <= now,
    )
    expired_condition = and_(
        IngestionJob.status == "processing",
        or_(
            IngestionJob.locked_at.is_(None),
            IngestionJob.locked_at <= expired_before,
        ),
    )
    db: Session = session_factory()
    try:
        job = db.scalar(
            select(IngestionJob)
            .where(or_(ready_condition, expired_condition))
            .order_by(IngestionJob.available_at, IngestionJob.created_at)
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        if job is None:
            return None

        if job.attempt_count >= job.max_attempts:
            job.status = "dead_letter"
            job.locked_at = None
            job.locked_by = None
            job.lease_token = None
            job.last_error = job.last_error or "Maximum job attempts exhausted"
            version = db.get(DocumentVersion, job.version_id)
            if version is not None and version.status != "published":
                version.status = "worker_failed"
                version.error_message = job.last_error
            db.commit()
            return None

        token = uuid.uuid4()
        job.status = "processing"
        job.attempt_count += 1
        job.locked_at = now
        job.locked_by = worker_id
        job.lease_token = token
        db.commit()
        return ClaimedJob(
            id=job.id,
            version_id=job.version_id,
            source_path=job.source_path,
            request_id=job.request_id,
            lease_token=token,
            attempt_count=job.attempt_count,
            max_attempts=job.max_attempts,
        )
    finally:
        db.close()


def renew_job_lease(
    job_id: UUID,
    lease_token: UUID,
    worker_id: str,
    session_factory=SessionLocal,
) -> bool:
    """Extend a lease only if this worker still owns its fencing token."""
    db: Session = session_factory()
    try:
        result = db.execute(
            update(IngestionJob)
            .where(
                IngestionJob.id == job_id,
                IngestionJob.status == "processing",
                IngestionJob.lease_token == lease_token,
                IngestionJob.locked_by == worker_id,
            )
            .values(
                locked_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
        )
        db.commit()
        return result.rowcount == 1
    finally:
        db.close()


def finalize_job(
    claim: ClaimedJob,
    worker_id: str,
    outcome: str,
    session_factory=SessionLocal,
    retry_base_seconds: float = 2,
    retry_max_seconds: float = 300,
    error_message: str | None = None,
) -> bool:
    """Finalize or reschedule a job if the lease token is still current."""
    db: Session = session_factory()
    try:
        job = db.scalar(
            select(IngestionJob)
            .where(IngestionJob.id == claim.id)
            .with_for_update()
        )
        if (
            job is None
            or job.status != "processing"
            or job.lease_token != claim.lease_token
            or job.locked_by != worker_id
        ):
            return False

        version = db.get(DocumentVersion, job.version_id)
        now = datetime.now(timezone.utc)
        job.locked_at = None
        job.locked_by = None
        job.lease_token = None

        if outcome in {"published", "unpublishable"}:
            job.status = "completed"
            job.completed_at = now
            job.last_error = None
        elif outcome == "stale":
            db.rollback()
            return False
        else:
            message = error_message or (
                version.error_message if version is not None else None
            ) or f"Worker returned outcome: {outcome}"
            job.last_error = message[:4000]
            if job.attempt_count >= job.max_attempts:
                job.status = "dead_letter"
                if version is not None and version.status != "published":
                    version.status = "worker_failed"
                    version.error_message = job.last_error
            else:
                delay = min(
                    retry_base_seconds * (2 ** (job.attempt_count - 1)),
                    retry_max_seconds,
                )
                job.status = "pending"
                job.available_at = now + timedelta(seconds=delay)
                if version is not None and version.status != "published":
                    version.status = "retrying"

        db.commit()
        return True
    finally:
        db.close()


class IngestionWorker:
    def __init__(
        self,
        session_factory=SessionLocal,
        processor=process_ingestion_version,
        worker_id: str | None = None,
        lease_seconds: float = 300,
        poll_seconds: float = 1,
        retry_base_seconds: float = 2,
        retry_max_seconds: float = 300,
    ):
        self.session_factory = session_factory
        self.processor = processor
        self.worker_id = worker_id or (
            f"{socket.gethostname()}-{os.getpid()}-{uuid.uuid4().hex[:8]}"
        )
        self.lease_seconds = lease_seconds
        self.poll_seconds = poll_seconds
        self.retry_base_seconds = retry_base_seconds
        self.retry_max_seconds = retry_max_seconds

    def run_once(self) -> bool:
        claim = claim_next_job(
            session_factory=self.session_factory,
            worker_id=self.worker_id,
            lease_seconds=self.lease_seconds,
        )
        if claim is None:
            return False

        stop_heartbeat = threading.Event()
        lease_lost = threading.Event()

        def heartbeat() -> None:
            interval = max(0.1, self.lease_seconds / 3)
            while not stop_heartbeat.wait(interval):
                if not renew_job_lease(
                    claim.id,
                    claim.lease_token,
                    self.worker_id,
                    session_factory=self.session_factory,
                ):
                    lease_lost.set()
                    return

        heartbeat_thread = threading.Thread(
            target=heartbeat,
            name=f"lease-{claim.id}",
            daemon=True,
        )
        heartbeat_thread.start()
        outcome = "worker_failed"
        error_message = None
        try:
            outcome = self.processor(
                version_id=claim.version_id,
                upload_path=claim.source_path,
                request_id=claim.request_id,
                session_factory=self.session_factory,
                job_id=claim.id,
                lease_token=claim.lease_token,
            ) or "worker_failed"
        except Exception as exc:
            error_message = f"{type(exc).__name__}: {exc}"
            logger.exception(
                "ingestion_job_execution_failed",
                extra={
                    "event": "ingestion_job_execution_failed",
                    "job_id": str(claim.id),
                    "version_id": str(claim.version_id),
                },
            )
        finally:
            stop_heartbeat.set()
            heartbeat_thread.join(timeout=1)

        if lease_lost.is_set():
            outcome = "stale"
        return finalize_job(
            claim=claim,
            worker_id=self.worker_id,
            outcome=outcome,
            session_factory=self.session_factory,
            retry_base_seconds=self.retry_base_seconds,
            retry_max_seconds=self.retry_max_seconds,
            error_message=error_message,
        )

    def run_forever(self, stop_event: threading.Event | None = None) -> None:
        logger.info(
            "ingestion_worker_started",
            extra={
                "event": "ingestion_worker_started",
                "worker_id": self.worker_id,
            },
        )
        while stop_event is None or not stop_event.is_set():
            try:
                worked = self.run_once()
                if not worked:
                    if stop_event is not None:
                        stop_event.wait(self.poll_seconds)
                    else:
                        time.sleep(self.poll_seconds)
            except KeyboardInterrupt:
                logger.info("ingestion_worker_stopped")
                return
            except Exception:
                logger.exception("ingestion_worker_poll_failed")
                if stop_event is not None:
                    stop_event.wait(self.poll_seconds)
                else:
                    time.sleep(self.poll_seconds)


def main() -> None:
    configure_logging()
    IngestionWorker().run_forever()


if __name__ == "__main__":
    main()
