"""add chunk provenance metadata

Revision ID: 3be92ac814d1
Revises: 16ef8f0cc48e
Create Date: 2026-11-17 22:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "3be92ac814d1"
down_revision: Union[str, Sequence[str], None] = "16ef8f0cc48e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "document_chunks",
        sa.Column("token_count", sa.Integer(), nullable=True),
    )
    op.add_column(
        "document_chunks",
        sa.Column("source_token_start", sa.Integer(), nullable=True),
    )
    op.add_column(
        "document_chunks",
        sa.Column("source_token_end", sa.Integer(), nullable=True),
    )
    op.add_column(
        "document_chunks",
        sa.Column("source_token_count", sa.Integer(), nullable=True),
    )
    op.add_column(
        "document_chunks",
        sa.Column("sources_json", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("document_chunks", "sources_json")
    op.drop_column("document_chunks", "source_token_count")
    op.drop_column("document_chunks", "source_token_end")
    op.drop_column("document_chunks", "source_token_start")
    op.drop_column("document_chunks", "token_count")
