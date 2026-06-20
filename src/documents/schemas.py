from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime  # noqa: TC003
from typing import TypedDict, final
from uuid import UUID  # noqa: TC003

from pydantic import BaseModel, Field, model_validator

from src.documents.status import DocumentStatus  # noqa: TC001
from src.documents.types import DocumentType

MetadataItem = dict[str, object]


@final
@dataclass(frozen=True, slots=True)
class CreateDocumentDTO:
    user_id: UUID
    title: str
    type: DocumentType
    collection_id: UUID | None = None
    source_url: str | None = None
    file_path: str | None = None
    file_size_bytes: int | None = None
    raw_content: str | None = None
    summary: str | None = None
    word_count: int | None = None
    language: str | None = None


@final
@dataclass(frozen=True, slots=True)
class ListDocumentsDTO:
    user_id: UUID
    limit: int = 50
    offset: int = 0
    collection_id: UUID | None = None
    status: DocumentStatus | None = None
    document_type: DocumentType | None = None
    tag_name: str | None = None


@final
@dataclass(frozen=True, slots=True)
class SearchDocumentsDTO:
    user_id: UUID
    query: str
    limit: int = 20
    collection_id: UUID | None = None
    status: DocumentStatus | None = None
    document_type: DocumentType | None = None
    tag_name: str | None = None


@final
@dataclass(frozen=True, slots=True)
class GetDocumentDTO:
    user_id: UUID
    document_id: UUID


@final
@dataclass(frozen=True, slots=True)
class GetDocumentChunkDTO:
    user_id: UUID
    document_id: UUID
    chunk_id: UUID


@final
@dataclass(frozen=True, slots=True)
class DeleteDocumentDTO:
    user_id: UUID
    document_id: UUID


@final
@dataclass(frozen=True, slots=True)
class RenameDocumentDTO:
    user_id: UUID
    document_id: UUID
    title: str


@final
@dataclass(frozen=True, slots=True)
class MoveDocumentDTO:
    user_id: UUID
    document_id: UUID
    collection_id: UUID | None


@final
@dataclass(frozen=True, slots=True)
class BulkDocumentOperationDTO:
    user_id: UUID
    document_ids: list[UUID]


@final
@dataclass(frozen=True, slots=True)
class BulkMoveDocumentsDTO:
    user_id: UUID
    document_ids: list[UUID]
    collection_id: UUID | None


@final
@dataclass(frozen=True, slots=True)
class BulkAddDocumentTagsDTO:
    user_id: UUID
    document_ids: list[UUID]
    tags: list[str]


@final
@dataclass(frozen=True, slots=True)
class RetryDocumentDTO:
    user_id: UUID
    document_id: UUID


@final
@dataclass(frozen=True, slots=True)
class ReprocessDocumentDTO:
    user_id: UUID
    document_id: UUID


@final
@dataclass(frozen=True, slots=True)
class DocumentDTO:
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
    entities: list[MetadataItem] | None
    categories: list[MetadataItem] | None
    is_duplicate: bool
    duplicate_of_id: UUID | None
    created_at: datetime
    updated_at: datetime | None
    visual_metadata: MetadataItem | None = None
    suggested_questions: list[str] | None = None
    tags: list[str] | None = None
    last_used_at: datetime | None = None
    query_count: int = 0
    citation_count: int = 0
    activity_temperature: str = "hot"


@final
@dataclass(frozen=True, slots=True)
class DocumentListDTO:
    items: list[DocumentDTO]
    total: int
    limit: int
    offset: int


@final
@dataclass(frozen=True, slots=True)
class DocumentSearchResultDTO:
    document: DocumentDTO
    snippet: str
    score: float | None
    chunk_id: UUID
    page_number: int | None


@final
@dataclass(frozen=True, slots=True)
class DocumentSearchDTO:
    items: list[DocumentSearchResultDTO]
    query: str
    total: int
    limit: int


@final
@dataclass(frozen=True, slots=True)
class DocumentConnectionDTO:
    document: DocumentDTO
    reasons: list[str]
    relationship_score: int


@final
@dataclass(frozen=True, slots=True)
class DocumentConnectionsDTO:
    items: list[DocumentConnectionDTO]
    document_id: UUID
    total: int
    limit: int


class EntityDTO(TypedDict):
    text: str
    label: str


class CategoryDTO(TypedDict):
    label: str
    score: float


@final
@dataclass(frozen=True, slots=True)
class TextChunkDTO:
    content: str
    chunk_index: int
    start_char: int
    end_char: int
    token_count: int


@final
@dataclass(frozen=True, slots=True)
class IngestTextDocumentDTO:
    user_id: UUID
    title: str
    raw_text: str
    collection_id: UUID | None = None
    type: DocumentType = DocumentType.TEXT
    source_url: str | None = None
    language: str | None = None


@final
@dataclass(frozen=True, slots=True)
class IngestDocumentDTO:
    user_id: UUID
    title: str
    type: DocumentType
    collection_id: UUID | None = None
    tags: list[str] | None = None
    source_url: str | None = None
    file_path: str | None = None
    file_size_bytes: int | None = None
    raw_content: str | None = None
    language: str | None = None


@final
@dataclass(frozen=True, slots=True)
class CreateNoteDTO:
    user_id: UUID
    title: str | None = None
    content: str | None = None
    collection_id: UUID | None = None
    language: str | None = None


@final
@dataclass(frozen=True, slots=True)
class UpdateNoteDTO:
    user_id: UUID
    note_id: UUID
    title: str
    content: str
    collection_id: UUID | None = None
    language: str | None = None


@final
@dataclass(frozen=True, slots=True)
class GetNoteDTO:
    user_id: UUID
    note_id: UUID


@final
@dataclass(frozen=True, slots=True)
class ListNotesDTO:
    user_id: UUID
    limit: int = 100
    offset: int = 0
    collection_id: UUID | None = None


@final
@dataclass(frozen=True, slots=True)
class ExternalIntakeItemDTO:
    id: UUID
    user_id: UUID
    api_key_id: UUID | None
    provider: str
    external_id: str | None
    idempotency_key: str | None
    title: str
    type: DocumentType
    collection_id: UUID | None
    tags: list[str]
    source_url: str | None
    status: str
    error_reason: str | None
    document_id: UUID | None
    payload_metadata: dict[str, object]
    created_at: datetime
    updated_at: datetime | None


@final
@dataclass(frozen=True, slots=True)
class ExternalIngestDTO:
    user_id: UUID
    api_key_id: UUID | None
    provider: str
    title: str
    type: DocumentType
    collection_id: UUID | None = None
    tags: list[str] | None = None
    source_url: str | None = None
    raw_content: str | None = None
    language: str | None = None
    external_id: str | None = None
    idempotency_key: str | None = None
    payload_metadata: dict[str, object] | None = None


@final
@dataclass(frozen=True, slots=True)
class ExternalIngestResultDTO:
    intake_item: ExternalIntakeItemDTO
    document: DocumentDTO | None


@final
@dataclass(frozen=True, slots=True)
class ExportedFileDTO:
    filename: str
    media_type: str
    content: bytes


@final
@dataclass(frozen=True, slots=True)
class NotionExportDTO:
    user_id: UUID
    title: str
    markdown: str
    parent_page_id: str | None = None


@final
@dataclass(frozen=True, slots=True)
class NotionExportResultDTO:
    page_id: str
    url: str | None


@final
@dataclass(frozen=True, slots=True)
class DocumentProcessingOutboxDTO:
    id: UUID
    document_id: UUID
    task_name: str
    status: str
    attempts: int
    locked_at: datetime | None
    last_error: str | None
    dispatched_at: datetime | None
    created_at: datetime
    updated_at: datetime | None


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
    def require_document_source(self) -> CreateDocumentRequest:
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
    def require_text_document_type(self) -> IngestTextDocumentRequest:
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
    def require_supported_source(self) -> IngestDocumentRequest:
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


class BulkMoveDocumentsRequest(BulkDocumentOperationRequest):
    collection_id: UUID | None = None


class BulkAddDocumentTagsRequest(BulkDocumentOperationRequest):
    tags: list[str] = Field(min_length=1, max_length=20)


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


class DocumentConnectionResponse(BaseModel):
    document: DocumentListItemResponse
    reasons: list[str]
    relationship_score: int


class DocumentConnectionsResponse(BaseModel):
    items: list[DocumentConnectionResponse]
    document_id: UUID
    total: int
    limit: int


class DocumentStatusResponse(BaseModel):
    document_id: UUID
    status: str
    progress: int
    message: str
    failure_reason: str | None = None
    timeline: list[DocumentProcessingStepResponse] = Field(default_factory=list)


class DocumentProcessingStepResponse(BaseModel):
    key: str
    label: str
    state: str
    progress: int
    message: str | None = None


class CreateNoteRequest(BaseModel):
    title: str | None = Field(default=None, max_length=120)
    content: str | None = None
    collection_id: UUID | None = None
    language: str | None = Field(default=None, max_length=10)


class UpdateNoteRequest(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    content: str = ""
    collection_id: UUID | None = None
    language: str | None = Field(default=None, max_length=10)


class NoteResponse(BaseModel):
    id: UUID
    collection_id: UUID | None
    title: str
    content: str
    status: DocumentStatus
    word_count: int
    language: str | None
    created_at: datetime
    updated_at: datetime | None


class NoteVersionResponse(BaseModel):
    id: UUID
    note_id: UUID
    version_number: int
    title: str
    content: str
    created_at: datetime


class NoteListItemResponse(BaseModel):
    id: UUID
    collection_id: UUID | None
    title: str
    status: DocumentStatus
    word_count: int
    language: str | None
    created_at: datetime
    updated_at: datetime | None


class NoteListResponse(BaseModel):
    items: list[NoteListItemResponse]
    total: int
    limit: int
    offset: int
