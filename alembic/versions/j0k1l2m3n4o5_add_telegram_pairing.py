"""add telegram pairing"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "j0k1l2m3n4o5"
down_revision: str | Sequence[str] | None = "i9j0k1l2m3n4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "telegram_pairing_codes",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("api_key_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("code_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["api_key_id"], ["api_keys.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_telegram_pairing_codes_api_key_id", "telegram_pairing_codes", ["api_key_id"])
    op.create_index("ix_telegram_pairing_codes_code_hash", "telegram_pairing_codes", ["code_hash"], unique=True)
    op.create_index("ix_telegram_pairing_codes_consumed_at", "telegram_pairing_codes", ["consumed_at"])
    op.create_index("ix_telegram_pairing_codes_expires_at", "telegram_pairing_codes", ["expires_at"])
    op.create_index("ix_telegram_pairing_codes_user_created", "telegram_pairing_codes", ["user_id", "created_at"])
    op.create_index("ix_telegram_pairing_codes_user_id", "telegram_pairing_codes", ["user_id"])

    op.create_table(
        "telegram_chat_bindings",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("api_key_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("chat_id", sa.String(length=64), nullable=False),
        sa.Column("chat_username", sa.String(length=255), nullable=True),
        sa.Column("chat_title", sa.String(length=255), nullable=True),
        sa.Column("paired_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["api_key_id"], ["api_keys.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_telegram_chat_bindings_api_key_id", "telegram_chat_bindings", ["api_key_id"])
    op.create_index("ix_telegram_chat_bindings_revoked_at", "telegram_chat_bindings", ["revoked_at"])
    op.create_index("ix_telegram_chat_bindings_user_created", "telegram_chat_bindings", ["user_id", "created_at"])
    op.create_index("ix_telegram_chat_bindings_user_id", "telegram_chat_bindings", ["user_id"])
    op.create_index(
        "uq_telegram_chat_bindings_active_chat",
        "telegram_chat_bindings",
        ["chat_id"],
        unique=True,
        postgresql_where=sa.text("revoked_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_telegram_chat_bindings_active_chat", table_name="telegram_chat_bindings")
    op.drop_index("ix_telegram_chat_bindings_user_id", table_name="telegram_chat_bindings")
    op.drop_index("ix_telegram_chat_bindings_user_created", table_name="telegram_chat_bindings")
    op.drop_index("ix_telegram_chat_bindings_revoked_at", table_name="telegram_chat_bindings")
    op.drop_index("ix_telegram_chat_bindings_api_key_id", table_name="telegram_chat_bindings")
    op.drop_table("telegram_chat_bindings")

    op.drop_index("ix_telegram_pairing_codes_user_id", table_name="telegram_pairing_codes")
    op.drop_index("ix_telegram_pairing_codes_user_created", table_name="telegram_pairing_codes")
    op.drop_index("ix_telegram_pairing_codes_expires_at", table_name="telegram_pairing_codes")
    op.drop_index("ix_telegram_pairing_codes_consumed_at", table_name="telegram_pairing_codes")
    op.drop_index("ix_telegram_pairing_codes_code_hash", table_name="telegram_pairing_codes")
    op.drop_index("ix_telegram_pairing_codes_api_key_id", table_name="telegram_pairing_codes")
    op.drop_table("telegram_pairing_codes")
