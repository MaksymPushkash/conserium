import uuid

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class PublicAskEventModel(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "public_ask_events"

    share_slug: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    collection_share_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("collection_shares.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    client_key: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    reason: Mapped[str | None] = mapped_column(String(128), nullable=True)
    query_text: Mapped[str] = mapped_column(Text, nullable=False)
    answer_share_slug: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
