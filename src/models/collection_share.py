import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from src.models.collection import CollectionModel
    from src.models.user import UserModel


class CollectionShareModel(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "collection_shares"

    collection_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("collections.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    slug: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    include_summaries: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    include_notes: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    ask_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    daily_ask_limit: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)

    collection: Mapped["CollectionModel"] = relationship()
    user: Mapped["UserModel"] = relationship()
