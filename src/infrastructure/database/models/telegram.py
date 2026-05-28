import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.database.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class TelegramPairingCodeModel(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "telegram_pairing_codes"
    __table_args__ = (
        Index("ix_telegram_pairing_codes_code_hash", "code_hash", unique=True),
        Index("ix_telegram_pairing_codes_user_created", "user_id", "created_at"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    api_key_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("api_keys.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    code_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)


class TelegramChatBindingModel(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "telegram_chat_bindings"
    __table_args__ = (
        Index(
            "uq_telegram_chat_bindings_active_chat",
            "chat_id",
            unique=True,
            postgresql_where=text("revoked_at IS NULL"),
        ),
        Index("ix_telegram_chat_bindings_user_created", "user_id", "created_at"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    api_key_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("api_keys.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    chat_id: Mapped[str] = mapped_column(String(64), nullable=False)
    chat_username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    chat_title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    paired_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
