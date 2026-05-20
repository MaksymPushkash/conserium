"""add repo syncs"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "b91f3a87c6d2"
down_revision: str | Sequence[str] | None = "a7c4e9d2b5f0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "repo_syncs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("collection_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("owner", sa.String(length=120), nullable=False),
        sa.Column("repo", sa.String(length=120), nullable=False),
        sa.Column("branch", sa.String(length=120), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["collection_id"], ["collections.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "owner", "repo", "branch", name="uq_repo_sync_user_repo_branch"),
    )
    op.create_index("ix_repo_syncs_collection_id", "repo_syncs", ["collection_id"])
    op.create_index("ix_repo_syncs_user_id", "repo_syncs", ["user_id"])
    op.create_table(
        "repo_sync_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("repo_sync_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("path", sa.String(length=1000), nullable=False),
        sa.Column("sha", sa.String(length=120), nullable=False),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["repo_sync_id"], ["repo_syncs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("repo_sync_id", "path", name="uq_repo_sync_item_path"),
    )
    op.create_index("ix_repo_sync_items_document_id", "repo_sync_items", ["document_id"])
    op.create_index("ix_repo_sync_items_repo_sync_id", "repo_sync_items", ["repo_sync_id"])


def downgrade() -> None:
    op.drop_index("ix_repo_sync_items_repo_sync_id", table_name="repo_sync_items")
    op.drop_index("ix_repo_sync_items_document_id", table_name="repo_sync_items")
    op.drop_table("repo_sync_items")
    op.drop_index("ix_repo_syncs_user_id", table_name="repo_syncs")
    op.drop_index("ix_repo_syncs_collection_id", table_name="repo_syncs")
    op.drop_table("repo_syncs")
