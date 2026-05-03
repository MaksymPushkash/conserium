from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from src.application.dtos.document_dtos import DocumentDTO, DocumentListDTO
from src.application.ports.cache.document_status_cache import DocumentStatusDTO
from src.domain.value_objects.document_status import DocumentStatus
from src.domain.value_objects.document_type import DocumentType

MetadataItem = dict[str, object]


class CreateDocumentRequest(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    type: DocumentType = DocumentType.TEXT
    collection_id: UUID | None = None
    source_url: str | None = None
    file_path: str | None = None
    file_size_bytes: int | None = Field(default=None, ge=0)
    raw_content: str | None = Field(default=None, max_length=1_000_000)
    summary: str | None = None
    word_count: int | None = Field(default=None, ge=0)
    language: str | None = Field(default=None, max_length=10)

    @model_validator(mode="after")
    def require_document_source(self) -> "CreateDocumentRequest":
        if self.raw_content is None and self.source_url is None and self.file_path is None:
            raise ValueError("one of raw_content, source_url, or file_path must be provided")
        return self


class IngestTextDocumentRequest(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    raw_text: str = Field(min_length=1, max_length=1_000_000)
    collection_id: UUID | None = None
    type: DocumentType = DocumentType.TEXT
    source_url: str | None = None
    language: str | None = Field(default=None, max_length=10)

    @model_validator(mode="after")
    def require_text_document_type(self) -> "IngestTextDocumentRequest":
        if self.type not in (DocumentType.TEXT, DocumentType.MARKDOWN):
            raise ValueError("ingest-text only supports TEXT or MARKDOWN documents")
        if not self.raw_text.strip():
            raise ValueError("raw_text cannot be empty")
        return self


class IngestDocumentRequest(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    type: DocumentType
    collection_id: UUID | None = None
    source_url: str | None = None
    file_path: str | None = None
    file_size_bytes: int | None = Field(default=None, ge=0)
    raw_content: str | None = Field(default=None, max_length=1_000_000)
    language: str | None = Field(default=None, max_length=10)

    @model_validator(mode="after")
    def require_supported_source(self) -> "IngestDocumentRequest":
        if self.type in (DocumentType.TEXT, DocumentType.MARKDOWN) and not (
            self.raw_content and self.raw_content.strip()
        ):
            raise ValueError("raw_content is required for text ingestion")
        if self.type in (DocumentType.URL, DocumentType.YOUTUBE) and self.source_url is None:
            raise ValueError(f"source_url is required for {self.type.value.lower()} ingestion")
        if self.type in (DocumentType.PDF, DocumentType.AUDIO, DocumentType.IMAGE) and self.file_path is None:
            raise ValueError(f"file_path is required for {self.type.value} ingestion")
        return self


class DocumentResponse(BaseModel):
    id: UUID
    user_id: UUID
    collection_id: UUID | None
    title: str
    type: DocumentType
    status: DocumentStatus
    source_url: str | None
    file_path: str | None
    file_size_bytes: int | None
    raw_content: str | None
    summary: str | None
    word_count: int | None
    language: str | None
    entities: list[MetadataItem] | None = None
    categories: list[MetadataItem] | None = None
    visual_metadata: MetadataItem | None = None
    tags: list[str] = Field(default_factory=list)
    is_duplicate: bool
    duplicate_of_id: UUID | None
    created_at: datetime
    updated_at: datetime | None

    @classmethod
    def from_dto(cls, dto: DocumentDTO) -> "DocumentResponse":
        return cls(
            id=dto.id,
            user_id=dto.user_id,
            collection_id=dto.collection_id,
            title=dto.title,
            type=dto.type,
            status=dto.status,
            source_url=dto.source_url,
            file_path=dto.file_path,
            file_size_bytes=dto.file_size_bytes,
            raw_content=dto.raw_content,
            summary=dto.summary,
            word_count=dto.word_count,
            language=dto.language,
            entities=dto.entities,
            categories=dto.categories,
            visual_metadata=dto.visual_metadata,
            tags=dto.tags or [],
            is_duplicate=dto.is_duplicate,
            duplicate_of_id=dto.duplicate_of_id,
            created_at=dto.created_at,
            updated_at=dto.updated_at,
        )


class DocumentListItemResponse(BaseModel):
    id: UUID
    user_id: UUID
    collection_id: UUID | None
    title: str
    type: DocumentType
    status: DocumentStatus
    source_url: str | None
    file_path: str | None
    file_size_bytes: int | None
    summary: str | None
    word_count: int | None
    language: str | None
    tags: list[str] = Field(default_factory=list)
    is_duplicate: bool
    duplicate_of_id: UUID | None
    created_at: datetime
    updated_at: datetime | None

    @classmethod
    def from_dto(cls, dto: DocumentDTO) -> "DocumentListItemResponse":
        return cls(
            id=dto.id,
            user_id=dto.user_id,
            collection_id=dto.collection_id,
            title=dto.title,
            type=dto.type,
            status=dto.status,
            source_url=dto.source_url,
            file_path=dto.file_path,
            file_size_bytes=dto.file_size_bytes,
            summary=dto.summary,
            word_count=dto.word_count,
            language=dto.language,
            tags=dto.tags or [],
            is_duplicate=dto.is_duplicate,
            duplicate_of_id=dto.duplicate_of_id,
            created_at=dto.created_at,
            updated_at=dto.updated_at,
        )


class DocumentListResponse(BaseModel):
    items: list[DocumentListItemResponse]
    total: int
    limit: int
    offset: int

    @classmethod
    def from_dto(cls, dto: DocumentListDTO) -> "DocumentListResponse":
        return cls(
            items=[DocumentListItemResponse.from_dto(item) for item in dto.items],
            total=dto.total,
            limit=dto.limit,
            offset=dto.offset,
        )


class DocumentStatusResponse(BaseModel):
    document_id: UUID
    status: str
    progress: int
    message: str

    @classmethod
    def from_dto(cls, dto: DocumentStatusDTO) -> "DocumentStatusResponse":
        return cls(
            document_id=dto.document_id,
            status=dto.status,
            progress=dto.progress,
            message=dto.message,
        )
