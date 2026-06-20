"""add learning paths

Revision ID: o5p6q7r8s9t0
Revises: n4o5p6q7r8s9
Create Date: 2026-06-02 00:00:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "o5p6q7r8s9t0"
down_revision: str | None = "n4o5p6q7r8s9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "learning_paths",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("collection_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("source_document_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("scope_type", sa.String(length=32), nullable=False),
        sa.Column("topic", sa.String(length=120), nullable=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("steps", postgresql.JSONB(astext_type=sa.Text()), server_default="[]", nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["collection_id"], ["collections.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["source_document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_learning_paths_collection_id", "learning_paths", ["collection_id"], unique=False)
    op.create_index("ix_learning_paths_source_document_id", "learning_paths", ["source_document_id"], unique=False)
    op.create_index("ix_learning_paths_user_created", "learning_paths", ["user_id", "created_at"], unique=False)
    op.create_index("ix_learning_paths_user_id", "learning_paths", ["user_id"], unique=False)
    op.create_index("ix_learning_paths_user_scope", "learning_paths", ["user_id", "scope_type"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_learning_paths_user_scope", table_name="learning_paths")
    op.drop_index("ix_learning_paths_user_id", table_name="learning_paths")
    op.drop_index("ix_learning_paths_user_created", table_name="learning_paths")
    op.drop_index("ix_learning_paths_source_document_id", table_name="learning_paths")
    op.drop_index("ix_learning_paths_collection_id", table_name="learning_paths")
    op.drop_table("learning_paths")
