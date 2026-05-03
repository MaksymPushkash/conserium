import uuid
from typing import TYPE_CHECKING

from pgvector.sqlalchemy import Vector
from sqlalchemy import BigInteger, Boolean, ForeignKey, Index, Integer, String, Text
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.domain.value_objects.document_status import DocumentStatus
from src.domain.value_objects.document_type import DocumentType
from src.infrastructure.database.models.base import (
    Base,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
    document_tags,
)

if TYPE_CHECKING:
    from src.infrastructure.database.models.chunk import ChunkModel
    from src.infrastructure.database.models.collection import CollectionModel
    from src.infrastructure.database.models.tag import TagModel
    from src.infrastructure.database.models.user import UserModel


class DocumentModel(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "documents"
    __table_args__ = (
        Index("ix_documents_user_created", "user_id", "created_at"),
        Index("ix_documents_user_status", "user_id", "status"),
        Index(
            "ix_documents_doc_embedding_hnsw",
            "doc_embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"doc_embedding": "vector_cosine_ops"},
        ),
    )
    
    user_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    collection_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("collections.id", ondelete="SET NULL"), nullable=True, index=True)
 
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    type: Mapped[DocumentType] = mapped_column(SQLEnum(DocumentType), nullable=False)
    status: Mapped[DocumentStatus] = mapped_column(SQLEnum(DocumentStatus), default=DocumentStatus.PENDING, nullable=False)
 
    source_url: Mapped[str | None] = mapped_column(Text) 
    file_path: Mapped[str | None] = mapped_column(String(500))  
    file_size_bytes: Mapped[int | None] = mapped_column(BigInteger)
 
    raw_content: Mapped[str | None] = mapped_column(Text)
    summary: Mapped[str | None] = mapped_column(Text) 
    word_count: Mapped[int | None] = mapped_column(Integer)
    language: Mapped[str | None] = mapped_column(String(10)) 

    entities: Mapped[list[dict[str, object]] | None] = mapped_column(JSONB)
    categories: Mapped[list[dict[str, object]] | None] = mapped_column(JSONB)
    visual_metadata: Mapped[dict[str, object] | None] = mapped_column(JSONB)
 
    doc_embedding: Mapped[list[float] | None] = mapped_column(Vector(1536))
 
    is_duplicate: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    duplicate_of_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("documents.id", ondelete="SET NULL"), nullable=True)
 
    user: Mapped["UserModel"] = relationship(back_populates="documents")
    collection: Mapped["CollectionModel | None"] = relationship(back_populates="documents")
    chunks: Mapped[list["ChunkModel"]] = relationship(back_populates="document", cascade="all, delete-orphan", passive_deletes=True)
    tags: Mapped[list["TagModel"]] = relationship(secondary=document_tags, back_populates="documents")
    duplicate_of: Mapped["DocumentModel | None"] = relationship("DocumentModel", remote_side="DocumentModel.id", foreign_keys="[DocumentModel.duplicate_of_id]")
 
