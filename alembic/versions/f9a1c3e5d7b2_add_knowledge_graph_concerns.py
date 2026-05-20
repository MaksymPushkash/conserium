from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "f9a1c3e5d7b2"
down_revision: str | Sequence[str] | None = "e4a9b7c2d5f8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "knowledge_graph_concerns",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("node_id", sa.String(length=240), nullable=True),
        sa.Column("node_kind", sa.String(length=40), nullable=True),
        sa.Column("node_label", sa.String(length=240), nullable=True),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_knowledge_graph_concerns_user_status",
        "knowledge_graph_concerns",
        ["user_id", "status"],
    )
    op.create_index(
        "ix_knowledge_graph_concerns_node",
        "knowledge_graph_concerns",
        ["user_id", "node_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_knowledge_graph_concerns_node", table_name="knowledge_graph_concerns")
    op.drop_index("ix_knowledge_graph_concerns_user_status", table_name="knowledge_graph_concerns")
    op.drop_table("knowledge_graph_concerns")
