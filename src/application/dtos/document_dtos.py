from dataclasses import dataclass
from datetime import datetime
from typing import final
from uuid import UUID

from src.domain.value_objects.document_status import DocumentStatus
from src.domain.value_objects.document_type import DocumentType


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


@final
@dataclass(frozen=True, slots=True)
class GetDocumentDTO:
    user_id: UUID
    document_id: UUID


@final
@dataclass(frozen=True, slots=True)
class DeleteDocumentDTO:
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
    is_duplicate: bool
    duplicate_of_id: UUID | None
    created_at: datetime
    updated_at: datetime | None


@final
@dataclass(frozen=True, slots=True)
class DocumentListDTO:
    items: list[DocumentDTO]
    total: int
    limit: int
    offset: int
