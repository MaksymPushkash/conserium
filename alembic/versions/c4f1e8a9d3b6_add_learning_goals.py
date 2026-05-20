"""add learning goals

Revision ID: c4f1e8a9d3b6
Revises: b91f3a87c6d2
Create Date: 2026-05-17 18:31:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "c4f1e8a9d3b6"
down_revision: str | None = "b91f3a87c6d2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "learning_goals",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("topic", sa.String(length=160), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("target_date", sa.Date(), nullable=True),
        sa.Column("status", sa.String(length=40), server_default="active", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_learning_goals_user_id", "learning_goals", ["user_id"])
    op.create_index("ix_learning_goals_user_status", "learning_goals", ["user_id", "status"])


def downgrade() -> None:
    op.drop_index("ix_learning_goals_user_status", table_name="learning_goals")
    op.drop_index("ix_learning_goals_user_id", table_name="learning_goals")
    op.drop_table("learning_goals")
