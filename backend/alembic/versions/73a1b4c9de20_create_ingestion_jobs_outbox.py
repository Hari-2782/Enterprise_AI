"""create transactional ingestion job outbox

Revision ID: 73a1b4c9de20
Revises: 3be92ac814d1
Create Date: 2026-11-17 22:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "73a1b4c9de20"
down_revision: Union[str, Sequence[str], None] = "3be92ac814d1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ingestion_jobs",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("version_id", sa.UUID(), nullable=False),
        sa.Column("source_path", sa.String(length=1024), nullable=False),
        sa.Column("request_id", sa.String(length=128), nullable=False),
        sa.Column(
            "status",
            sa.String(length=30),
            server_default="pending",
            nullable=False,
        ),
        sa.Column(
            "attempt_count",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
        sa.Column(
            "max_attempts",
            sa.Integer(),
            server_default="5",
            nullable=False,
        ),
        sa.Column(
            "available_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("locked_by", sa.String(length=128), nullable=True),
        sa.Column("lease_token", sa.UUID(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "attempt_count >= 0",
            name="ck_ingestion_job_attempt_count_nonnegative",
        ),
        sa.CheckConstraint(
            "max_attempts > 0",
            name="ck_ingestion_job_max_attempts_positive",
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'processing', 'completed', 'dead_letter')",
            name="ck_ingestion_job_status",
        ),
        sa.ForeignKeyConstraint(
            ["version_id"],
            ["document_versions.id"],
            name="fk_ingestion_jobs_version_id_document_versions",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "version_id",
            name="uq_ingestion_job_version_id",
        ),
    )
    op.create_index(
        "ix_ingestion_jobs_ready",
        "ingestion_jobs",
        ["status", "available_at", "created_at"],
    )
    op.create_index(
        "ix_ingestion_jobs_lease",
        "ingestion_jobs",
        ["status", "locked_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_ingestion_jobs_lease", table_name="ingestion_jobs")
    op.drop_index("ix_ingestion_jobs_ready", table_name="ingestion_jobs")
    op.drop_table("ingestion_jobs")
