from datetime import UTC, datetime
from math import isfinite
from uuid import UUID

from src.domain.constants import EMBEDDING_DIMENSIONS as DEFAULT_EMBEDDING_DIMENSIONS
from src.domain.value_objects.document_status import DocumentStatus
from src.domain.value_objects.document_type import DocumentType

MetadataItem = dict[str, object]


class DocumentEntity:
    EMBEDDING_DIMENSIONS = DEFAULT_EMBEDDING_DIMENSIONS

    def __init__(
        self,
        *,
        id: UUID,
        user_id: UUID,
        collection_id: UUID | None,
        title: str,
        type: DocumentType,
        status: DocumentStatus,
        source_url: str | None,
        file_path: str | None,
        file_size_bytes: int | None,
        raw_content: str | None,
        summary: str | None,
        word_count: int | None,
        language: str | None,
        entities: list[MetadataItem] | None = None,
        categories: list[MetadataItem] | None = None,
        doc_embedding: list[float] | None,
        is_duplicate: bool,
        duplicate_of_id: UUID | None,
        created_at: datetime,
        updated_at: datetime | None,
        visual_metadata: MetadataItem | None = None,
        suggested_questions: list[str] | None = None,
        tags: list[str] | None = None,
    ) -> None:
        self._id = id
        self._user_id = user_id
        self._collection_id = collection_id
        self._title = self._validate_required_text(title, "title")
        self._type = type
        self._status = status
        self._source_url = self._validate_optional_text(source_url, "source_url")
        self._file_path = self._validate_optional_text(file_path, "file_path")
        self._file_size_bytes = self._validate_non_negative_optional_int(file_size_bytes, "file_size_bytes")
        self._raw_content = self._validate_optional_text(raw_content, "raw_content")
        self._summary = self._validate_optional_text(summary, "summary")
        self._word_count = self._validate_non_negative_optional_int(word_count, "word_count")
        self._language = self._validate_language(language)
        self._entities = entities
        self._categories = categories
        self._visual_metadata = visual_metadata.copy() if visual_metadata is not None else None
        self._suggested_questions = list(suggested_questions) if suggested_questions is not None else []
        self._tags = list(tags) if tags is not None else []
        self._doc_embedding = self._validate_embedding(doc_embedding)
        self._is_duplicate = is_duplicate
        self._duplicate_of_id = duplicate_of_id
        self._created_at = self._validate_timestamp(created_at, "created_at")
        self._updated_at = self._validate_optional_timestamp(updated_at, "updated_at")
        self._validate_duplicate_state()
        self._validate_updated_at_order()

    @property
    def id(self) -> UUID:
        return self._id

    @property
    def user_id(self) -> UUID:
        return self._user_id

    @property
    def collection_id(self) -> UUID | None:
        return self._collection_id

    @property
    def title(self) -> str:
        return self._title

    @property
    def type(self) -> DocumentType:
        return self._type

    @property
    def status(self) -> DocumentStatus:
        return self._status

    @property
    def source_url(self) -> str | None:
        return self._source_url

    @property
    def file_path(self) -> str | None:
        return self._file_path

    @property
    def file_size_bytes(self) -> int | None:
        return self._file_size_bytes

    @property
    def raw_content(self) -> str | None:
        return self._raw_content

    @property
    def summary(self) -> str | None:
        return self._summary

    @property
    def word_count(self) -> int | None:
        return self._word_count

    @property
    def language(self) -> str | None:
        return self._language

    @property
    def entities(self) -> list[MetadataItem] | None:
        if self._entities is None:
            return None
        return list(self._entities)

    @property
    def categories(self) -> list[MetadataItem] | None:
        if self._categories is None:
            return None
        return list(self._categories)

    @property
    def doc_embedding(self) -> list[float] | None:
        if self._doc_embedding is None:
            return None
        return self._doc_embedding.copy()

    @property
    def visual_metadata(self) -> MetadataItem | None:
        if self._visual_metadata is None:
            return None
        return self._visual_metadata.copy()

    @property
    def suggested_questions(self) -> list[str]:
        return list(self._suggested_questions)

    @property
    def tags(self) -> list[str]:
        return list(self._tags)

    @property
    def is_duplicate(self) -> bool:
        return self._is_duplicate

    @property
    def duplicate_of_id(self) -> UUID | None:
        return self._duplicate_of_id

    @property
    def created_at(self) -> datetime:
        return self._created_at

    @property
    def updated_at(self) -> datetime | None:
        return self._updated_at

    def snapshot(self) -> "DocumentEntity":
        return DocumentEntity(
            id=self._id,
            user_id=self._user_id,
            collection_id=self._collection_id,
            title=self._title,
            type=self._type,
            status=self._status,
            source_url=self._source_url,
            file_path=self._file_path,
            file_size_bytes=self._file_size_bytes,
            raw_content=self._raw_content,
            summary=self._summary,
            word_count=self._word_count,
            language=self._language,
            entities=self.entities,
            categories=self.categories,
            visual_metadata=self.visual_metadata,
            suggested_questions=self.suggested_questions,
            doc_embedding=self.doc_embedding,
            is_duplicate=self._is_duplicate,
            duplicate_of_id=self._duplicate_of_id,
            created_at=self._created_at,
            updated_at=self._updated_at,
            tags=self.tags,
        )

    @classmethod
    def create(
        cls,
        *,
        id: UUID,
        user_id: UUID,
        title: str,
        type: DocumentType,
        collection_id: UUID | None = None,
        source_url: str | None = None,
        file_path: str | None = None,
        file_size_bytes: int | None = None,
        raw_content: str | None = None,
        summary: str | None = None,
        word_count: int | None = None,
        language: str | None = None,
        tags: list[str] | None = None,
        doc_embedding: list[float] | None = None,
    ) -> "DocumentEntity":
        return cls(
            id=id,
            user_id=user_id,
            collection_id=collection_id,
            title=title,
            type=type,
            status=DocumentStatus.PENDING,
            source_url=source_url,
            file_path=file_path,
            file_size_bytes=file_size_bytes,
            raw_content=raw_content,
            summary=summary,
            word_count=word_count,
            language=language,
            entities=None,
            categories=None,
            doc_embedding=doc_embedding,
            is_duplicate=False,
            duplicate_of_id=None,
            created_at=datetime.now(UTC),
            updated_at=None,
            visual_metadata=None,
            suggested_questions=[],
            tags=list(tags or []),
        )

    def rename(self, title: str) -> None:
        new_title = self._validate_required_text(title, "title")
        if new_title == self._title:
            return
        self._title = new_title
        self._touch()

    def assign_collection(self, collection_id: UUID | None) -> None:
        if collection_id == self._collection_id:
            return
        self._collection_id = collection_id
        self._touch()

    def update_content(
        self,
        *,
        raw_content: str | None,
        word_count: int | None = None,
        language: str | None = None,
    ) -> None:
        new_raw_content = self._validate_optional_text(raw_content, "raw_content")
        new_word_count = self._validate_non_negative_optional_int(word_count, "word_count")
        new_language = self._validate_language(language)
        if (
            new_raw_content == self._raw_content
            and new_word_count == self._word_count
            and new_language == self._language
        ):
            return
        self._raw_content = new_raw_content
        self._word_count = new_word_count
        self._language = new_language
        self._touch()

    def update_summary(self, summary: str | None) -> None:
        new_summary = self._validate_optional_text(summary, "summary")
        if new_summary == self._summary:
            return
        self._summary = new_summary
        self._touch()

    def update_embedding(self, doc_embedding: list[float] | None) -> None:
        new_embedding = self._validate_embedding(doc_embedding)
        if new_embedding == self._doc_embedding:
            return
        self._doc_embedding = new_embedding
        self._touch()

    def update_enrichment(
        self,
        entities: list[MetadataItem] | None = None,
        categories: list[MetadataItem] | None = None,
        tags: list[str] | None = None,
    ) -> None:
        if entities is not None:
            self._entities = entities
        if categories is not None:
            self._categories = categories
        if tags is not None:
            self._tags = list(tags)
        if entities is not None or categories is not None or tags is not None:
            self._touch()

    def update_visual_metadata(self, visual_metadata: MetadataItem | None) -> None:
        if visual_metadata == self._visual_metadata:
            return
        self._visual_metadata = visual_metadata.copy() if visual_metadata is not None else None
        self._touch()

    def update_suggested_questions(self, suggested_questions: list[str]) -> None:
        if suggested_questions == self._suggested_questions:
            return
        self._suggested_questions = list(suggested_questions)
        self._touch()

    def mark_queued(self) -> None:
        self._set_status(DocumentStatus.QUEUED)

    def mark_processing(self) -> None:
        self._set_status(DocumentStatus.PROCESSING)

    def mark_ready(self) -> None:
        self._set_status(DocumentStatus.READY)

    def mark_failed(self) -> None:
        self._set_status(DocumentStatus.FAILED)

    def mark_duplicate(self, duplicate_of_id: UUID) -> None:
        if duplicate_of_id == self._id:
            raise ValueError("document cannot be marked as a duplicate of itself")
        if self._is_duplicate and self._duplicate_of_id == duplicate_of_id:
            return
        self._is_duplicate = True
        self._duplicate_of_id = duplicate_of_id
        self._touch()

    def clear_duplicate(self) -> None:
        if not self._is_duplicate and self._duplicate_of_id is None:
            return
        self._is_duplicate = False
        self._duplicate_of_id = None
        self._touch()

    def _set_status(self, status: DocumentStatus) -> None:
        if status == self._status:
            return
        self._status = status
        self._touch()

    def _touch(self) -> None:
        self._updated_at = datetime.now(UTC)

    @classmethod
    def _validate_required_text(cls, value: str, field_name: str) -> str:
        if not value.strip():
            raise ValueError(f"{field_name} cannot be empty")
        return value.strip()

    @classmethod
    def _validate_optional_text(cls, value: str | None, field_name: str) -> str | None:
        if value is None:
            return None
        if not value.strip():
            raise ValueError(f"{field_name} cannot be empty when provided")
        return value

    @classmethod
    def _validate_non_negative_optional_int(cls, value: int | None, field_name: str) -> int | None:
        if value is not None and value < 0:
            raise ValueError(f"{field_name} cannot be negative")
        return value

    @classmethod
    def _validate_language(cls, language: str | None) -> str | None:
        normalized = cls._validate_optional_text(language, "language")
        if normalized is not None and len(normalized) > 10:
            raise ValueError("language cannot exceed 10 characters")
        return normalized

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
        if value is None:
            return None
        return cls._validate_timestamp(value, field_name)

    def _validate_duplicate_state(self) -> None:
        if self._duplicate_of_id == self._id:
            raise ValueError("document cannot be a duplicate of itself")
        if self._is_duplicate and self._duplicate_of_id is None:
            raise ValueError("duplicate documents must reference the original document")
        if not self._is_duplicate and self._duplicate_of_id is not None:
            raise ValueError("non-duplicate documents cannot reference an original document")

    def _validate_updated_at_order(self) -> None:
        if self._updated_at is not None and self._updated_at < self._created_at:
            raise ValueError("updated_at cannot be earlier than created_at")

    def __repr__(self) -> str:
        return (
            "DocumentEntity("
            f"id={self._id}, "
            f"user_id={self._user_id}, "
            f"title={self._title!r}, "
            f"type={self._type.value}, "
            f"status={self._status.value}"
            ")"
        )
