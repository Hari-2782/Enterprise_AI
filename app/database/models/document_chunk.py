import uuid

from datetime import datetime

from sqlalchemy import (
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


class DocumentChunk(Base):
    __tablename__ = "document_chunks"

    __table_args__ = (
        UniqueConstraint(
            "version_id",
            "chunk_index",
            name="uq_version_chunk_index",
        ),
        UniqueConstraint(
            "search_document_key",
            name="uq_search_document_key",
        ),
        Index("ix_chunks_version", "version_id"),
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

    chunk_index: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    search_document_key: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )

    content: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    chunk_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )

    section_path: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    token_count: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    source_token_start: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    source_token_end: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    source_token_count: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    sources_json: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    page_number: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    index_status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="pending",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    version: Mapped["DocumentVersion"] = relationship(
        back_populates="chunks",
    )
