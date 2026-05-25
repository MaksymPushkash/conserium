"""add topic overrides"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "c8f2e4a9b6d1"
down_revision: str | Sequence[str] | None = "b5e7c9a1d3f2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "topic_overrides",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_name", sa.String(length=100), nullable=False),
        sa.Column("display_name", sa.String(length=100), nullable=False),
        sa.Column("pinned", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("ignored", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "source_name", name="uq_topic_override_user_source"),
    )
    op.create_index("ix_topic_overrides_user_id", "topic_overrides", ["user_id"])
    op.create_index("ix_topic_overrides_user_display", "topic_overrides", ["user_id", "display_name"])


def downgrade() -> None:
    op.drop_index("ix_topic_overrides_user_display", table_name="topic_overrides")
    op.drop_index("ix_topic_overrides_user_id", table_name="topic_overrides")
    op.drop_table("topic_overrides")
