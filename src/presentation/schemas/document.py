from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

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
        if self.type in (DocumentType.PDF, DocumentType.IMAGE) and self.file_path is None:
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
    suggested_questions: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    last_used_at: datetime | None = None
    query_count: int = 0
    citation_count: int = 0
    activity_temperature: str = "hot"
    is_duplicate: bool
    duplicate_of_id: UUID | None
    created_at: datetime
    updated_at: datetime | None


class DocumentChunkResponse(BaseModel):
    id: UUID
    document_id: UUID
    content: str
    chunk_index: int
    start_char: int | None
    end_char: int | None
    page_number: int | None
    token_count: int | None


class RenameDocumentRequest(BaseModel):
    title: str = Field(min_length=1, max_length=500)


class MoveDocumentRequest(BaseModel):
    collection_id: UUID | None = None


class BulkDocumentOperationRequest(BaseModel):
    document_ids: list[UUID] = Field(min_length=1, max_length=100)


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
    suggested_questions: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    last_used_at: datetime | None = None
    query_count: int = 0
    citation_count: int = 0
    activity_temperature: str = "hot"
    is_duplicate: bool
    duplicate_of_id: UUID | None
    created_at: datetime
    updated_at: datetime | None


class DocumentListResponse(BaseModel):
    items: list[DocumentListItemResponse]
    total: int
    limit: int
    offset: int


class DocumentSearchResultResponse(BaseModel):
    document: DocumentListItemResponse
    snippet: str
    score: float | None
    chunk_id: UUID
    page_number: int | None


class DocumentSearchResponse(BaseModel):
    items: list[DocumentSearchResultResponse]
    query: str
    total: int
    limit: int


class DocumentQuestionHistoryItemResponse(BaseModel):
    query_text: str
    answer_text: str | None
    result_count: int
    created_at: datetime


class DocumentQuestionHistoryResponse(BaseModel):
    items: list[DocumentQuestionHistoryItemResponse]
    document_id: UUID
    limit: int


class DocumentStatusResponse(BaseModel):
    document_id: UUID
    status: str
    progress: int
    message: str
    failure_reason: str | None = None
    timeline: list["DocumentProcessingStepResponse"] = Field(default_factory=list)


class DocumentProcessingStepResponse(BaseModel):
    key: str
    label: str
    state: str
    progress: int
    message: str | None = None
