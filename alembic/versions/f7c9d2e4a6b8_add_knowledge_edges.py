"""add knowledge edges

Revision ID: f7c9d2e4a6b8
Revises: e6a4b8c1d2f9
Create Date: 2026-05-17 23:18:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "f7c9d2e4a6b8"
down_revision: str | None = "e6a4b8c1d2f9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "knowledge_edges",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_document_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("target_document_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("relation_type", sa.String(length=80), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("evidence", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["source_document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["target_document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_knowledge_edges_source_target", "knowledge_edges", ["source_document_id", "target_document_id"])
    op.create_index("ix_knowledge_edges_user_relation", "knowledge_edges", ["user_id", "relation_type"])


def downgrade() -> None:
    op.drop_index("ix_knowledge_edges_user_relation", table_name="knowledge_edges")
    op.drop_index("ix_knowledge_edges_source_target", table_name="knowledge_edges")
    op.drop_table("knowledge_edges")
