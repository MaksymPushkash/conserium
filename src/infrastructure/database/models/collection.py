import uuid
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.infrastructure.database.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from src.infrastructure.database.models.document import DocumentModel
    from src.infrastructure.database.models.user import UserModel


class CollectionModel(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "collections"
    __table_args__ = (
        UniqueConstraint("user_id", "name", name="uq_collection_user_name"),
    )
    
    user_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    color: Mapped[str | None] = mapped_column(String(7))
    
    user: Mapped["UserModel"] = relationship(back_populates="collections")
    documents: Mapped[list["DocumentModel"]] = relationship(back_populates="collection", passive_deletes=True)
    

    
    