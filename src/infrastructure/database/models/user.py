from typing import TYPE_CHECKING

from sqlalchemy import Boolean, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.infrastructure.database.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from src.infrastructure.database.models.chat import ChatSessionModel
    from src.infrastructure.database.models.collection import CollectionModel
    from src.infrastructure.database.models.document import DocumentModel
    from src.infrastructure.database.models.search_query import SearchQueryModel
    from src.infrastructure.database.models.tag import TagModel

class UserModel(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "users"
    
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(100))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    preferences: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    
    documents: Mapped[list["DocumentModel"]] = relationship(back_populates="user", passive_deletes=True)
    collections: Mapped[list["CollectionModel"]] = relationship(back_populates="user", passive_deletes=True)
    tags: Mapped[list["TagModel"]] = relationship(back_populates="user", passive_deletes=True)
    search_queries: Mapped[list["SearchQueryModel"]] = relationship(back_populates="user", passive_deletes=True)
    chat_sessions: Mapped[list["ChatSessionModel"]] = relationship(back_populates="user", passive_deletes=True)
