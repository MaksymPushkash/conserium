import uuid
from datetime import UTC, datetime
from math import isfinite
from typing import TYPE_CHECKING

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, ForeignKey, Index, Integer, Text, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.kit.constants import EMBEDDING_DIMENSIONS
from src.models.base import Base, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from src.models.document import DocumentModel



class ChunkModel(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "chunks"
    __table_args__ = (
        Index(
            "ix_chunks_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
        Index("ix_chunks_document_index", "document_id", "chunk_index"),
    )
    
    document_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    
    content: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIMENSIONS), nullable=False)
    
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    start_char: Mapped[int | None] = mapped_column(Integer)
    end_char: Mapped[int | None] = mapped_column(Integer)
    page_number: Mapped[int | None] = mapped_column(Integer)
    token_count: Mapped[int | None] = mapped_column(Integer)
    
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    
    document: Mapped["DocumentModel"] = relationship(back_populates="chunks")

    EMBEDDING_DIMENSIONS = EMBEDDING_DIMENSIONS

    def __init__(self, **kwargs: object) -> None:
        if "content" in kwargs:
            kwargs["content"] = self._validate_content(str(kwargs["content"]))
        if "embedding" in kwargs:
            kwargs["embedding"] = self._validate_embedding(kwargs["embedding"])  # type: ignore[arg-type]
        for field_name in ("chunk_index", "start_char", "end_char", "page_number", "token_count"):
            if field_name not in kwargs:
                continue
            value = kwargs[field_name]
            if field_name == "chunk_index":
                kwargs[field_name] = self._validate_non_negative_int(value, field_name)  # type: ignore[arg-type]
            else:
                kwargs[field_name] = self._validate_non_negative_optional_int(value, field_name)  # type: ignore[arg-type]
        kwargs.setdefault("created_at", datetime.now(UTC))
        super().__init__(**kwargs)
        self._validate_timestamp(self.created_at, "created_at")
        if self.start_char is not None and self.end_char is not None and self.end_char < self.start_char:
            raise ValueError("end_char cannot be smaller than start_char")

    @classmethod
    def create(
        cls,
        *,
        id: uuid.UUID,
        document_id: uuid.UUID,
        content: str,
        embedding: list[float],
        chunk_index: int,
        start_char: int | None = None,
        end_char: int | None = None,
        page_number: int | None = None,
        token_count: int | None = None,
    ) -> "ChunkModel":
        return cls(
            id=id,
            document_id=document_id,
            content=content,
            embedding=embedding,
            chunk_index=chunk_index,
            start_char=start_char,
            end_char=end_char,
            page_number=page_number,
            token_count=token_count,
        )

    def update_embedding(self, embedding: list[float]) -> None:
        self.embedding = self._validate_embedding(embedding)

    @staticmethod
    def _validate_content(content: str) -> str:
        if not content.strip():
            raise ValueError("content cannot be empty")
        return content

    @staticmethod
    def _validate_non_negative_int(value: int, field_name: str) -> int:
        if value < 0:
            raise ValueError(f"{field_name} cannot be negative")
        return value

    @classmethod
    def _validate_non_negative_optional_int(cls, value: int | None, field_name: str) -> int | None:
        if value is None:
            return None
        return cls._validate_non_negative_int(value, field_name)

    @classmethod
    def _validate_embedding(cls, embedding: list[float]) -> list[float]:
        if len(embedding) != cls.EMBEDDING_DIMENSIONS:
            raise ValueError(f"embedding must have {cls.EMBEDDING_DIMENSIONS} dimensions")
        if not all(isfinite(float(value)) for value in embedding):
            raise ValueError("embedding must contain only finite numeric values")
        return [float(value) for value in embedding]

    @staticmethod
    def _validate_timestamp(value: datetime, field_name: str) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError(f"{field_name} must be timezone-aware")
        return value
