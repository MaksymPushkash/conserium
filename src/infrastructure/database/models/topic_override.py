import uuid

from sqlalchemy import Boolean, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.database.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class TopicOverrideModel(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "topic_overrides"
    __table_args__ = (
        UniqueConstraint("user_id", "source_name", name="uq_topic_override_user_source"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    source_name: Mapped[str] = mapped_column(String(100), nullable=False)
    display_name: Mapped[str] = mapped_column(String(100), nullable=False)
    pinned: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    ignored: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
