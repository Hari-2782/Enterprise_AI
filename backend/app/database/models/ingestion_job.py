import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base


class IngestionJob(Base):
    """Transactional outbox row for processing one document version."""

    __tablename__ = "ingestion_jobs"

    __table_args__ = (
        UniqueConstraint(
            "version_id",
            name="uq_ingestion_job_version_id",
        ),
        CheckConstraint(
            "attempt_count >= 0",
            name="ck_ingestion_job_attempt_count_nonnegative",
        ),
        CheckConstraint(
            "max_attempts > 0",
            name="ck_ingestion_job_max_attempts_positive",
        ),
        CheckConstraint(
            "status IN ('pending', 'processing', 'completed', 'dead_letter')",
            name="ck_ingestion_job_status",
        ),
        Index(
            "ix_ingestion_jobs_ready",
            "status",
            "available_at",
            "created_at",
        ),
        Index(
            "ix_ingestion_jobs_lease",
            "status",
            "locked_at",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("document_versions.id", ondelete="CASCADE"),
        nullable=False,
    )

    source_path: Mapped[str] = mapped_column(
        String(1024),
        nullable=False,
    )

    request_id: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="pending",
        server_default="pending",
    )

    attempt_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )

    max_attempts: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=5,
        server_default="5",
    )

    available_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    locked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    locked_by: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
    )

    lease_token: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
    )

    last_error: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    version: Mapped["DocumentVersion"] = relationship(
        back_populates="ingestion_job",
    )
