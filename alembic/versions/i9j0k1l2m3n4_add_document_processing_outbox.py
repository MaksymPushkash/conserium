"""add document processing outbox"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "i9j0k1l2m3n4"
down_revision: str | Sequence[str] | None = "h8i9j0k1l2m3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "document_processing_outbox",
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("task_name", sa.String(length=120), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("dispatched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_document_processing_outbox_document_id", "document_processing_outbox", ["document_id"])
    op.create_index("ix_document_processing_outbox_status", "document_processing_outbox", ["status"])
    op.create_index(
        "uq_document_processing_outbox_active_task",
        "document_processing_outbox",
        ["document_id", "task_name"],
        unique=True,
        postgresql_where=sa.text("status != 'dispatched'"),
    )


def downgrade() -> None:
    op.drop_index("uq_document_processing_outbox_active_task", table_name="document_processing_outbox")
    op.drop_index("ix_document_processing_outbox_status", table_name="document_processing_outbox")
    op.drop_index("ix_document_processing_outbox_document_id", table_name="document_processing_outbox")
    op.drop_table("document_processing_outbox")
