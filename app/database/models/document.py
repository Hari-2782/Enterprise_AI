import uuid

from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKeyConstraint,
    Index,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base


class Document(Base):
    __tablename__ = "documents"

    __table_args__ = (
        Index("ix_documents_department", "department"),
        ForeignKeyConstraint(
            ["id", "current_version_id"],
            ["document_versions.document_id", "document_versions.id"],
            name="fk_documents_current_version",
            use_alter=True,
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    title: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    department: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    # current_version_id: Mapped[uuid.UUID | None] = mapped_column(
    #     UUID(as_uuid=True),
    #     ForeignKey(
    #         "document_versions.id",
    #         name="fk_documents_current_version",
    #         use_alter=True,
    #     ),
    #     nullable=True,
    # )
    current_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    versions: Mapped[list["DocumentVersion"]] = relationship(
        back_populates="document",
        foreign_keys="DocumentVersion.document_id",
    )

    current_version: Mapped["DocumentVersion | None"] = relationship(
        primaryjoin=(
            "and_("
            "Document.current_version_id == DocumentVersion.id, "
            "Document.id == DocumentVersion.document_id"
            ")"
        ),
        foreign_keys=[current_version_id],
        post_update=True,
    )