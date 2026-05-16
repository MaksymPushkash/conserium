import uuid
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.infrastructure.database.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, document_topics

if TYPE_CHECKING:
    from src.infrastructure.database.models.document import DocumentModel
    from src.infrastructure.database.models.user import UserModel


class TopicModel(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "topics"
    __table_args__ = (
        UniqueConstraint("user_id", "name", name="uq_topic_user_name"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)

    user: Mapped["UserModel"] = relationship()
    documents: Mapped[list["DocumentModel"]] = relationship(secondary=document_topics, back_populates="topics")
