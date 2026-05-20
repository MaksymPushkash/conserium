import uuid
from typing import Any

from sqlalchemy import ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.infrastructure.database.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class ExternalConnectionModel(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "external_connections"
    __table_args__ = (UniqueConstraint("user_id", "provider", name="uq_external_connection_user_provider"),)

    user_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    workspace_id: Mapped[str | None] = mapped_column(String(160), nullable=True)
    workspace_name: Mapped[str | None] = mapped_column(String(240), nullable=True)
    access_token_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    bot_id: Mapped[str | None] = mapped_column(String(160), nullable=True)
    owner: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    default_parent_page_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    default_parent_page_title: Mapped[str | None] = mapped_column(String(300), nullable=True)

    user = relationship("UserModel")
