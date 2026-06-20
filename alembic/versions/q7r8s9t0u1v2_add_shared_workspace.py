"""add shared workspace

Revision ID: q7r8s9t0u1v2
Revises: p6q7r8s9t0u1
Create Date: 2026-06-02 00:00:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "q7r8s9t0u1v2"
down_revision: str | None = "p6q7r8s9t0u1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "collection_members",
        sa.Column("collection_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("invited_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["collection_id"], ["collections.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["invited_by_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("collection_id", "email", name="uq_collection_member_email"),
        sa.UniqueConstraint("collection_id", "user_id", name="uq_collection_member_user"),
    )
    op.create_index("ix_collection_members_collection_id", "collection_members", ["collection_id"], unique=False)
    op.create_index("ix_collection_members_collection_role", "collection_members", ["collection_id", "role"], unique=False)
    op.create_index("ix_collection_members_user_id", "collection_members", ["user_id"], unique=False)

    op.create_table(
        "collection_audit_events",
        sa.Column("collection_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_type", sa.String(length=80), nullable=False),
        sa.Column("event_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["collection_id"], ["collections.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_collection_audit_collection_created", "collection_audit_events", ["collection_id", "created_at"], unique=False)
    op.create_index("ix_collection_audit_events_actor_user_id", "collection_audit_events", ["actor_user_id"], unique=False)
    op.create_index("ix_collection_audit_events_collection_id", "collection_audit_events", ["collection_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_collection_audit_events_collection_id", table_name="collection_audit_events")
    op.drop_index("ix_collection_audit_events_actor_user_id", table_name="collection_audit_events")
    op.drop_index("ix_collection_audit_collection_created", table_name="collection_audit_events")
    op.drop_table("collection_audit_events")
    op.drop_index("ix_collection_members_user_id", table_name="collection_members")
    op.drop_index("ix_collection_members_collection_role", table_name="collection_members")
    op.drop_index("ix_collection_members_collection_id", table_name="collection_members")
    op.drop_table("collection_members")
