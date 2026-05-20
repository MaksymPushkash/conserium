"""add collection shares"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "a7c4e9d2b5f0"
down_revision: str | Sequence[str] | None = "f4d9b8a6c2e1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "collection_shares",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("collection_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("slug", sa.String(length=64), nullable=False),
        sa.Column("include_summaries", sa.Boolean(), nullable=False),
        sa.Column("include_notes", sa.Boolean(), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["collection_id"], ["collections.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_collection_shares_collection_id", "collection_shares", ["collection_id"])
    op.create_index("ix_collection_shares_revoked_at", "collection_shares", ["revoked_at"])
    op.create_index("ix_collection_shares_slug", "collection_shares", ["slug"], unique=True)
    op.create_index("ix_collection_shares_user_id", "collection_shares", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_collection_shares_user_id", table_name="collection_shares")
    op.drop_index("ix_collection_shares_slug", table_name="collection_shares")
    op.drop_index("ix_collection_shares_revoked_at", table_name="collection_shares")
    op.drop_index("ix_collection_shares_collection_id", table_name="collection_shares")
    op.drop_table("collection_shares")
