import uuid
from datetime import UTC, datetime
from math import isfinite
from typing import TYPE_CHECKING

from pgvector.sqlalchemy import Vector
from sqlalchemy import BigInteger, Boolean, ForeignKey, Index, Integer, String, Text
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.documents.status import DocumentStatus
from src.documents.types import DocumentType
from src.kit.constants import EMBEDDING_DIMENSIONS
from src.models.base import (
    Base,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
    document_tags,
    document_topics,
)

if TYPE_CHECKING:
    from src.models.chunk import ChunkModel
    from src.models.collection import CollectionModel
    from src.models.tag import TagModel
    from src.models.topic import TopicModel
    from src.models.user import UserModel


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
    suggested_questions: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
 
    doc_embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIMENSIONS))
 
    is_duplicate: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    duplicate_of_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("documents.id", ondelete="SET NULL"), nullable=True)
 
    user: Mapped["UserModel"] = relationship(back_populates="documents")
    collection: Mapped["CollectionModel | None"] = relationship(back_populates="documents")
    chunks: Mapped[list["ChunkModel"]] = relationship(back_populates="document", cascade="all, delete-orphan", passive_deletes=True)
    tag_models: Mapped[list["TagModel"]] = relationship(secondary=document_tags, back_populates="documents")
    topics: Mapped[list["TopicModel"]] = relationship(secondary=document_topics, back_populates="documents")
    duplicate_of: Mapped["DocumentModel | None"] = relationship("DocumentModel", remote_side="DocumentModel.id", foreign_keys="[DocumentModel.duplicate_of_id]")

    EMBEDDING_DIMENSIONS = EMBEDDING_DIMENSIONS

    def __init__(self, **kwargs: object) -> None:
        tag_names = kwargs.pop("tags", None)
        if "title" in kwargs:
            kwargs["title"] = self._validate_required_text(str(kwargs["title"]), "title")
        for field_name in ("source_url", "file_path", "raw_content", "summary"):
            if field_name in kwargs:
                kwargs[field_name] = self._validate_optional_text(kwargs[field_name], field_name)  # type: ignore[arg-type]
        if "file_size_bytes" in kwargs:
            kwargs["file_size_bytes"] = self._validate_non_negative_optional_int(
                kwargs["file_size_bytes"], "file_size_bytes"  # type: ignore[arg-type]
            )
        if "word_count" in kwargs:
            kwargs["word_count"] = self._validate_non_negative_optional_int(
                kwargs["word_count"], "word_count"  # type: ignore[arg-type]
            )
        if "language" in kwargs:
            kwargs["language"] = self._validate_language(kwargs["language"])  # type: ignore[arg-type]
        if "doc_embedding" in kwargs:
            kwargs["doc_embedding"] = self._validate_embedding(kwargs["doc_embedding"])  # type: ignore[arg-type]
        kwargs.setdefault("status", DocumentStatus.PENDING)
        kwargs.setdefault("entities", None)
        kwargs.setdefault("categories", None)
        kwargs.setdefault("visual_metadata", None)
        kwargs.setdefault("suggested_questions", [])
        kwargs.setdefault("is_duplicate", False)
        kwargs.setdefault("duplicate_of_id", None)
        kwargs.setdefault("created_at", datetime.now(UTC))
        kwargs.setdefault("updated_at", None)
        super().__init__(**kwargs)
        self._pending_tag_names = list(tag_names) if isinstance(tag_names, list) else []
        self._validate_duplicate_state()
        self._validate_timestamp(self.created_at, "created_at")
        self._validate_optional_timestamp(self.updated_at, "updated_at")
        if self.updated_at is not None and self.updated_at < self.created_at:
            raise ValueError("updated_at cannot be earlier than created_at")

    @property
    def tags(self) -> list[str]:
        if "tag_models" in self.__dict__:
            return [tag.name for tag in self.tag_models]
        return list(getattr(self, "_pending_tag_names", []))

    def snapshot(self) -> "DocumentModel":
        return DocumentModel(
            id=self.id,
            user_id=self.user_id,
            collection_id=self.collection_id,
            title=self.title,
            type=self.type,
            status=self.status,
            source_url=self.source_url,
            file_path=self.file_path,
            file_size_bytes=self.file_size_bytes,
            raw_content=self.raw_content,
            summary=self.summary,
            word_count=self.word_count,
            language=self.language,
            entities=list(self.entities) if self.entities is not None else None,
            categories=list(self.categories) if self.categories is not None else None,
            visual_metadata=dict(self.visual_metadata) if self.visual_metadata is not None else None,
            suggested_questions=list(self.suggested_questions),
            tags=self.tags,
            doc_embedding=list(self.doc_embedding) if self.doc_embedding is not None else None,
            is_duplicate=self.is_duplicate,
            duplicate_of_id=self.duplicate_of_id,
            created_at=self.created_at,
            updated_at=self.updated_at,
        )

    @classmethod
    def create(
        cls,
        *,
        id: uuid.UUID,
        user_id: uuid.UUID,
        title: str,
        type: DocumentType,
        collection_id: uuid.UUID | None = None,
        source_url: str | None = None,
        file_path: str | None = None,
        file_size_bytes: int | None = None,
        raw_content: str | None = None,
        summary: str | None = None,
        word_count: int | None = None,
        language: str | None = None,
        tags: list[str] | None = None,
        doc_embedding: list[float] | None = None,
    ) -> "DocumentModel":
        return cls(
            id=id,
            user_id=user_id,
            collection_id=collection_id,
            title=title,
            type=type,
            source_url=source_url,
            file_path=file_path,
            file_size_bytes=file_size_bytes,
            raw_content=raw_content,
            summary=summary,
            word_count=word_count,
            language=language,
            tags=tags or [],
            doc_embedding=doc_embedding,
        )

    def rename(self, title: str) -> None:
        title = self._validate_required_text(title, "title")
        if title != self.title:
            self.title = title
            self._touch()

    def assign_collection(self, collection_id: uuid.UUID | None) -> None:
        if collection_id != self.collection_id:
            self.collection_id = collection_id
            self._touch()

    def update_content(self, *, raw_content: str | None, word_count: int | None = None, language: str | None = None) -> None:
        raw_content = self._validate_optional_text(raw_content, "raw_content")
        word_count = self._validate_non_negative_optional_int(word_count, "word_count")
        language = self._validate_language(language)
        if (raw_content, word_count, language) != (self.raw_content, self.word_count, self.language):
            self.raw_content = raw_content
            self.word_count = word_count
            self.language = language
            self._touch()

    def update_summary(self, summary: str | None) -> None:
        summary = self._validate_optional_text(summary, "summary")
        if summary != self.summary:
            self.summary = summary
            self._touch()

    def update_embedding(self, doc_embedding: list[float] | None) -> None:
        doc_embedding = self._validate_embedding(doc_embedding)
        if doc_embedding != self.doc_embedding:
            self.doc_embedding = doc_embedding
            self._touch()

    def update_enrichment(
        self,
        entities: list[dict[str, object]] | None = None,
        categories: list[dict[str, object]] | None = None,
        tags: list[str] | None = None,
    ) -> None:
        if entities is not None:
            self.entities = entities
        if categories is not None:
            self.categories = categories
        if tags is not None:
            self._pending_tag_names = list(tags)
        if entities is not None or categories is not None or tags is not None:
            self._touch()

    def update_visual_metadata(self, visual_metadata: dict[str, object] | None) -> None:
        if visual_metadata != self.visual_metadata:
            self.visual_metadata = dict(visual_metadata) if visual_metadata is not None else None
            self._touch()

    def update_suggested_questions(self, suggested_questions: list[str]) -> None:
        if suggested_questions != self.suggested_questions:
            self.suggested_questions = list(suggested_questions)
            self._touch()

    def mark_queued(self) -> None:
        self._set_status(DocumentStatus.QUEUED)

    def mark_processing(self) -> None:
        self._set_status(DocumentStatus.PROCESSING)

    def mark_ready(self) -> None:
        self._set_status(DocumentStatus.READY)

    def mark_failed(self) -> None:
        self._set_status(DocumentStatus.FAILED)

    def mark_duplicate(self, duplicate_of_id: uuid.UUID) -> None:
        if duplicate_of_id == self.id:
            raise ValueError("document cannot be marked as a duplicate of itself")
        if not self.is_duplicate or self.duplicate_of_id != duplicate_of_id:
            self.is_duplicate = True
            self.duplicate_of_id = duplicate_of_id
            self._touch()

    def clear_duplicate(self) -> None:
        if self.is_duplicate or self.duplicate_of_id is not None:
            self.is_duplicate = False
            self.duplicate_of_id = None
            self._touch()

    def _set_status(self, status: DocumentStatus) -> None:
        if status != self.status:
            self.status = status
            self._touch()

    def _touch(self) -> None:
        self.updated_at = datetime.now(UTC)

    @staticmethod
    def _validate_required_text(value: str, field_name: str) -> str:
        if not value.strip():
            raise ValueError(f"{field_name} cannot be empty")
        return value.strip()

    @staticmethod
    def _validate_optional_text(value: str | None, field_name: str) -> str | None:
        if value is None:
            return None
        if not value.strip():
            raise ValueError(f"{field_name} cannot be empty when provided")
        return value

    @staticmethod
    def _validate_non_negative_optional_int(value: int | None, field_name: str) -> int | None:
        if value is not None and value < 0:
            raise ValueError(f"{field_name} cannot be negative")
        return value

    @classmethod
    def _validate_language(cls, language: str | None) -> str | None:
        language = cls._validate_optional_text(language, "language")
        if language is not None and len(language) > 10:
            raise ValueError("language cannot exceed 10 characters")
        return language

    @classmethod
    def _validate_embedding(cls, embedding: list[float] | None) -> list[float] | None:
        if embedding is None:
            return None
        if len(embedding) != cls.EMBEDDING_DIMENSIONS:
            raise ValueError(f"doc_embedding must have {cls.EMBEDDING_DIMENSIONS} dimensions")
        if not all(isfinite(float(value)) for value in embedding):
            raise ValueError("doc_embedding must contain only finite numeric values")
        return [float(value) for value in embedding]

    @staticmethod
    def _validate_timestamp(value: datetime, field_name: str) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError(f"{field_name} must be timezone-aware")
        return value

    @classmethod
    def _validate_optional_timestamp(cls, value: datetime | None, field_name: str) -> datetime | None:
        if value is not None:
            cls._validate_timestamp(value, field_name)
        return value

    def _validate_duplicate_state(self) -> None:
        if self.duplicate_of_id == self.id:
            raise ValueError("document cannot be a duplicate of itself")
        if self.is_duplicate and self.duplicate_of_id is None:
            raise ValueError("duplicate documents must reference the original document")
        if not self.is_duplicate and self.duplicate_of_id is not None:
            raise ValueError("non-duplicate documents cannot reference an original document")
