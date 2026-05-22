import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.domain.constants import EMBEDDING_DIMENSIONS
from src.infrastructure.database.models.base import Base, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from src.infrastructure.database.models.collection import CollectionModel
    from src.infrastructure.database.models.user import UserModel

from src.domain.value_objects.query_type import QueryType


class SearchQueryModel(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "search_queries"
    __table_args__ = (
        Index("ix_search_queries_user_created", "user_id", "created_at"),
    )
    
    
    user_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    collection_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("collections.id", ondelete="SET NULL"), nullable=True)
    document_ids: Mapped[list[str]] = mapped_column(JSONB, default=list, server_default="[]", nullable=False)
    
    query_text: Mapped[str] = mapped_column(Text, nullable=False)
    query_type: Mapped[QueryType] = mapped_column(SQLEnum(QueryType), nullable=False)
    query_embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIMENSIONS))
    
    result_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    answer_text: Mapped[str | None] = mapped_column(Text)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    
    ragas_faithfulness: Mapped[float | None] = mapped_column(Float)
    ragas_answer_relevancy: Mapped[float | None] = mapped_column(Float)
    ragas_context_recall: Mapped[float | None] = mapped_column(Float)
    
    langfuse_trace_id: Mapped[str | None] = mapped_column(String(100))
    
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    
    user: Mapped["UserModel"] = relationship(back_populates="search_queries")
    collection: Mapped["CollectionModel | None"] = relationship()
    
