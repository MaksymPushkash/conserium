"""add comparisons"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "f6a7b8c9d0e1"
down_revision: str | Sequence[str] | None = "e5b6d7c8a9f0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "comparisons",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("collection_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("left_document_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("right_document_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("left_title", sa.String(length=500), nullable=False),
        sa.Column("right_title", sa.String(length=500), nullable=False),
        sa.Column("dimensions", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("markdown", sa.Text(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("evidence_rows", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("source_metadata", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(["collection_id"], ["collections.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["left_document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["right_document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_comparisons_user_id", "comparisons", ["user_id"])
    op.create_index("ix_comparisons_collection_id", "comparisons", ["collection_id"])
    op.create_index("ix_comparisons_user_created", "comparisons", ["user_id", "created_at"])
    op.create_index("ix_comparisons_user_collection_created", "comparisons", ["user_id", "collection_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_comparisons_user_collection_created", table_name="comparisons")
    op.drop_index("ix_comparisons_user_created", table_name="comparisons")
    op.drop_index("ix_comparisons_collection_id", table_name="comparisons")
    op.drop_index("ix_comparisons_user_id", table_name="comparisons")
    op.drop_table("comparisons")
