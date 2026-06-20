"""add answer shares"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "l2m3n4o5p6q7"
down_revision: str | Sequence[str] | None = "k1l2m3n4o5p6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "answer_shares",
        sa.Column("slug", sa.String(length=64), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("collection_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("conversation_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("public_collection_slug", sa.String(length=64), nullable=True),
        sa.Column("query_text", sa.Text(), nullable=False),
        sa.Column("answer_text", sa.Text(), nullable=False),
        sa.Column("sources", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["collection_id"], ["collections.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_answer_shares_collection_id", "answer_shares", ["collection_id"])
    op.create_index("ix_answer_shares_conversation_id", "answer_shares", ["conversation_id"])
    op.create_index("ix_answer_shares_public_collection_slug", "answer_shares", ["public_collection_slug"])
    op.create_index("ix_answer_shares_revoked_at", "answer_shares", ["revoked_at"])
    op.create_index("ix_answer_shares_slug", "answer_shares", ["slug"], unique=True)
    op.create_index("ix_answer_shares_user_created", "answer_shares", ["user_id", "created_at"])
    op.create_index("ix_answer_shares_user_id", "answer_shares", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_answer_shares_user_id", table_name="answer_shares")
    op.drop_index("ix_answer_shares_user_created", table_name="answer_shares")
    op.drop_index("ix_answer_shares_slug", table_name="answer_shares")
    op.drop_index("ix_answer_shares_revoked_at", table_name="answer_shares")
    op.drop_index("ix_answer_shares_public_collection_slug", table_name="answer_shares")
    op.drop_index("ix_answer_shares_conversation_id", table_name="answer_shares")
    op.drop_index("ix_answer_shares_collection_id", table_name="answer_shares")
    op.drop_table("answer_shares")
