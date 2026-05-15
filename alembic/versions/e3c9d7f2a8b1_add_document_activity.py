"""add document activity"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "e3c9d7f2a8b1"
down_revision: str | Sequence[str] | None = "d8b21a7f0c44"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "document_activity",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_type", sa.String(length=40), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_document_activity_user_id", "document_activity", ["user_id"])
    op.create_index("ix_document_activity_document_id", "document_activity", ["document_id"])
    op.create_index("ix_document_activity_event_type", "document_activity", ["event_type"])
    op.create_index("ix_document_activity_user_document_created", "document_activity", ["user_id", "document_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_document_activity_user_document_created", table_name="document_activity")
    op.drop_index("ix_document_activity_event_type", table_name="document_activity")
    op.drop_index("ix_document_activity_document_id", table_name="document_activity")
    op.drop_index("ix_document_activity_user_id", table_name="document_activity")
    op.drop_table("document_activity")
