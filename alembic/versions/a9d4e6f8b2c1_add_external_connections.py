"""add external connections

Revision ID: a9d4e6f8b2c1
Revises: f7c9d2e4a6b8
Create Date: 2026-05-17 23:50:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "a9d4e6f8b2c1"
down_revision: str | None = "f7c9d2e4a6b8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "external_connections",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("workspace_id", sa.String(length=160), nullable=True),
        sa.Column("workspace_name", sa.String(length=240), nullable=True),
        sa.Column("access_token_encrypted", sa.Text(), nullable=False),
        sa.Column("bot_id", sa.String(length=160), nullable=True),
        sa.Column("owner", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "provider", name="uq_external_connection_user_provider"),
    )
    op.create_index(op.f("ix_external_connections_user_id"), "external_connections", ["user_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_external_connections_user_id"), table_name="external_connections")
    op.drop_table("external_connections")
