"""add public ask hardening"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "m3n4o5p6q7r8"
down_revision: str | Sequence[str] | None = "l2m3n4o5p6q7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("collection_shares", sa.Column("ask_enabled", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.add_column("collection_shares", sa.Column("daily_ask_limit", sa.Integer(), nullable=False, server_default="100"))
    op.create_table(
        "public_ask_events",
        sa.Column("share_slug", sa.String(length=64), nullable=False),
        sa.Column("collection_share_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("owner_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("client_key", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("reason", sa.String(length=128), nullable=True),
        sa.Column("query_text", sa.Text(), nullable=False),
        sa.Column("answer_share_slug", sa.String(length=64), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["collection_share_id"], ["collection_shares.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_public_ask_events_answer_share_slug", "public_ask_events", ["answer_share_slug"])
    op.create_index("ix_public_ask_events_client_key", "public_ask_events", ["client_key"])
    op.create_index("ix_public_ask_events_collection_share_id", "public_ask_events", ["collection_share_id"])
    op.create_index("ix_public_ask_events_owner_created", "public_ask_events", ["owner_user_id", "created_at"])
    op.create_index("ix_public_ask_events_owner_user_id", "public_ask_events", ["owner_user_id"])
    op.create_index("ix_public_ask_events_share_created", "public_ask_events", ["share_slug", "created_at"])
    op.create_index("ix_public_ask_events_share_slug", "public_ask_events", ["share_slug"])
    op.create_index("ix_public_ask_events_status", "public_ask_events", ["status"])


def downgrade() -> None:
    op.drop_index("ix_public_ask_events_status", table_name="public_ask_events")
    op.drop_index("ix_public_ask_events_share_slug", table_name="public_ask_events")
    op.drop_index("ix_public_ask_events_share_created", table_name="public_ask_events")
    op.drop_index("ix_public_ask_events_owner_user_id", table_name="public_ask_events")
    op.drop_index("ix_public_ask_events_owner_created", table_name="public_ask_events")
    op.drop_index("ix_public_ask_events_collection_share_id", table_name="public_ask_events")
    op.drop_index("ix_public_ask_events_client_key", table_name="public_ask_events")
    op.drop_index("ix_public_ask_events_answer_share_slug", table_name="public_ask_events")
    op.drop_table("public_ask_events")
    op.drop_column("collection_shares", "daily_ask_limit")
    op.drop_column("collection_shares", "ask_enabled")
