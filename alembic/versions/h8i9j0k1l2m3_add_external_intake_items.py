"""add external intake items"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "h8i9j0k1l2m3"
down_revision: str | Sequence[str] | None = "g7h8i9j0k1l2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "external_intake_items",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("api_key_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("collection_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("provider", sa.String(length=80), nullable=False),
        sa.Column("external_id", sa.String(length=200), nullable=True),
        sa.Column("idempotency_key", sa.String(length=200), nullable=True),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column(
            "type",
            postgresql.ENUM("TEXT", "PDF", "URL", "YOUTUBE", "IMAGE", "MARKDOWN", name="documenttype", create_type=False),
            nullable=False,
        ),
        sa.Column("tags", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("raw_content", sa.Text(), nullable=True),
        sa.Column("language", sa.String(length=10), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("error_reason", sa.Text(), nullable=True),
        sa.Column("payload_metadata", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["api_key_id"], ["api_keys.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["collection_id"], ["collections.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_external_intake_items_api_key_id", "external_intake_items", ["api_key_id"])
    op.create_index("ix_external_intake_items_collection_id", "external_intake_items", ["collection_id"])
    op.create_index("ix_external_intake_items_document_id", "external_intake_items", ["document_id"])
    op.create_index("ix_external_intake_items_status", "external_intake_items", ["status"])
    op.create_index("ix_external_intake_items_user_id", "external_intake_items", ["user_id"])
    op.create_index("ix_external_intake_user_created", "external_intake_items", ["user_id", "created_at"])
    op.create_index(
        "ix_external_intake_user_provider_key",
        "external_intake_items",
        ["user_id", "provider", "idempotency_key"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_external_intake_user_provider_key", table_name="external_intake_items")
    op.drop_index("ix_external_intake_user_created", table_name="external_intake_items")
    op.drop_index("ix_external_intake_items_user_id", table_name="external_intake_items")
    op.drop_index("ix_external_intake_items_status", table_name="external_intake_items")
    op.drop_index("ix_external_intake_items_document_id", table_name="external_intake_items")
    op.drop_index("ix_external_intake_items_collection_id", table_name="external_intake_items")
    op.drop_index("ix_external_intake_items_api_key_id", table_name="external_intake_items")
    op.drop_table("external_intake_items")
