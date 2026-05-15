from dataclasses import dataclass
from datetime import datetime
from typing import final
from uuid import UUID

from src.domain.value_objects.document_status import DocumentStatus
from src.domain.value_objects.document_type import DocumentType

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


@final
@dataclass(frozen=True, slots=True)
class DocumentChunkDTO:
    id: UUID
    document_id: UUID
    content: str
    chunk_index: int
    start_char: int | None
    end_char: int | None
    page_number: int | None
    token_count: int | None


@final
@dataclass(frozen=True, slots=True)
class DocumentListDTO:
    items: list[DocumentDTO]
    total: int
    limit: int
    offset: int
