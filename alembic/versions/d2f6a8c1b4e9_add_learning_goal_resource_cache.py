"""add learning goal resource cache

Revision ID: d2f6a8c1b4e9
Revises: b0e5c7d9a3f1
Create Date: 2026-05-18 16:40:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "d2f6a8c1b4e9"
down_revision: str | None = "b0e5c7d9a3f1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "learning_goal_resources",
        sa.Column("goal_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("area", sa.String(length=160), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("search_query", sa.String(length=300), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("url", sa.Text(), nullable=True),
        sa.Column("excerpt", sa.Text(), nullable=True),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("refreshed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(["goal_id"], ["learning_goals.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_learning_goal_resources_goal_id"), "learning_goal_resources", ["goal_id"])
    op.create_index(op.f("ix_learning_goal_resources_refreshed_at"), "learning_goal_resources", ["refreshed_at"])


def downgrade() -> None:
    op.drop_index(op.f("ix_learning_goal_resources_refreshed_at"), table_name="learning_goal_resources")
    op.drop_index(op.f("ix_learning_goal_resources_goal_id"), table_name="learning_goal_resources")
    op.drop_table("learning_goal_resources")
