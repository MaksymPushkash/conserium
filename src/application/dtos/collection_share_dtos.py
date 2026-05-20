from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from src.domain.value_objects.document_status import DocumentStatus
from src.domain.value_objects.document_type import DocumentType


@dataclass(frozen=True, slots=True)
class CollectionShareDTO:
    id: UUID
    collection_id: UUID
    user_id: UUID
    slug: str
    include_summaries: bool
    include_notes: bool
    revoked_at: datetime | None
    created_at: datetime
    updated_at: datetime | None


@dataclass(frozen=True, slots=True)
class PublicCollectionDocumentDTO:
    id: UUID
    title: str
    type: DocumentType
    status: DocumentStatus
    source_url: str | None
    summary: str | None
    word_count: int | None
    language: str | None
    tags: list[str]
    created_at: datetime
    updated_at: datetime | None


@dataclass(frozen=True, slots=True)
class PublicCollectionDTO:
    id: UUID
    name: str
    description: str | None
    color: str | None
    documents: list[PublicCollectionDocumentDTO]
    created_at: datetime
    updated_at: datetime | None
