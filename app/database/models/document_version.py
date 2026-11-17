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


class DocumentVersion(Base):
    __tablename__ = "document_versions"

    __table_args__ = (
        UniqueConstraint(
            "document_id",
            "id",
            name="uq_document_version_document_id_id",
        ),
        UniqueConstraint(
            "document_id",
            "version_number",
            name="uq_document_version_number",
        ),
        UniqueConstraint(
            "document_id",
            "content_hash",
            name="uq_document_version_content_hash",
        ),
        CheckConstraint(
            "version_number >= 1",
            name="ck_version_number_positive",
        ),
        CheckConstraint(
            "expected_chunks >= 0",
            name="ck_expected_chunks_nonnegative",
        ),
        CheckConstraint(
            "indexed_chunks >= 0",
            name="ck_indexed_chunks_nonnegative",
        ),
        Index("ix_versions_status", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
    )

    version_number: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    filename: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    content_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="uploaded",
    )

    expected_chunks: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    indexed_chunks: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    error_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    document: Mapped["Document"] = relationship(
        back_populates="versions",
        foreign_keys=[document_id],
    )

    chunks: Mapped[list["DocumentChunk"]] = relationship(
        back_populates="version",
        cascade="all, delete-orphan",
    )

    ingestion_job: Mapped["IngestionJob | None"] = relationship(
        back_populates="version",
        cascade="all, delete-orphan",
        uselist=False,
    )
