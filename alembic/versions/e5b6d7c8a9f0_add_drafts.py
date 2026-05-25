"""add drafts"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "e5b6d7c8a9f0"
down_revision: str | Sequence[str] | None = "d4e8f2a6c9b1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "drafts",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("collection_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("current_version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("template_id", sa.String(length=80), nullable=False),
        sa.Column("scope_type", sa.String(length=32), nullable=False),
        sa.Column("topic", sa.String(length=100), nullable=True),
        sa.Column("knowledge_gap_id", sa.String(length=160), nullable=True),
        sa.Column("scope_metadata", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("markdown", sa.Text(), nullable=False),
        sa.Column("source_metadata", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("gaps", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["collection_id"], ["collections.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_drafts_user_id", "drafts", ["user_id"])
    op.create_index("ix_drafts_collection_id", "drafts", ["collection_id"])
    op.create_index("ix_drafts_user_updated", "drafts", ["user_id", "updated_at"])
    op.create_index("ix_drafts_user_collection_updated", "drafts", ["user_id", "collection_id", "updated_at"])

    op.create_table(
        "draft_versions",
        sa.Column("draft_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("template_id", sa.String(length=80), nullable=False),
        sa.Column("scope_type", sa.String(length=32), nullable=False),
        sa.Column("collection_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("topic", sa.String(length=100), nullable=True),
        sa.Column("knowledge_gap_id", sa.String(length=160), nullable=True),
        sa.Column("scope_metadata", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("markdown", sa.Text(), nullable=False),
        sa.Column("source_metadata", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("gaps", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(["collection_id"], ["collections.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["draft_id"], ["drafts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_draft_versions_draft_id", "draft_versions", ["draft_id"])
    op.create_index("ix_draft_versions_user_id", "draft_versions", ["user_id"])
    op.create_index("ix_draft_versions_draft_number", "draft_versions", ["draft_id", "version_number"])
    op.create_index("ix_draft_versions_user_draft", "draft_versions", ["user_id", "draft_id"])


def downgrade() -> None:
    op.drop_index("ix_draft_versions_user_draft", table_name="draft_versions")
    op.drop_index("ix_draft_versions_draft_number", table_name="draft_versions")
    op.drop_index("ix_draft_versions_user_id", table_name="draft_versions")
    op.drop_index("ix_draft_versions_draft_id", table_name="draft_versions")
    op.drop_table("draft_versions")
    op.drop_index("ix_drafts_user_collection_updated", table_name="drafts")
    op.drop_index("ix_drafts_user_updated", table_name="drafts")
    op.drop_index("ix_drafts_collection_id", table_name="drafts")
    op.drop_index("ix_drafts_user_id", table_name="drafts")
    op.drop_table("drafts")
