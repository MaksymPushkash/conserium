from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from datetime import datetime
    from uuid import UUID

    from src.documents.types import DocumentType
    from src.models.chunk import ChunkModel
    from src.models.document import DocumentModel


@dataclass(frozen=True, slots=True)
class ChunkSearchResult:
    chunk: ChunkModel
    document_title: str | None
    score: float | None = None


DocumentActivityEventType = Literal["created", "opened", "queried", "cited_in_answer", "summarized", "exported"]


@dataclass(frozen=True, slots=True)
class DocumentActivitySummary:
    document_id: UUID
    last_used_at: datetime | None
    query_count: int
    citation_count: int


@dataclass(frozen=True, slots=True)
class DocumentActivityOverview:
    hot_documents: int
    cold_documents: int
    forgotten_documents: int
    active_documents: int
    query_count: int
    citation_count: int


@dataclass(frozen=True, slots=True)
class RelatedDocumentRecord:
    document: DocumentModel
    reasons: list[str]
    relationship_score: int


@dataclass(slots=True)
class ExternalIntakeItemRecord:
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
    raw_content: str | None
    language: str | None
    status: str
    error_reason: str | None
    document_id: UUID | None
    payload_metadata: dict[str, object]
    created_at: datetime
    updated_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class NoteVersionRecord:
    id: UUID
    note_id: UUID
    user_id: UUID
    version_number: int
    title: str
    content: str
    created_at: datetime | None = None


__all__ = [
    "ChunkSearchResult",
    "DocumentActivityEventType",
    "DocumentActivityOverview",
    "DocumentActivitySummary",
    "ExternalIntakeItemRecord",
    "NoteVersionRecord",
    "RelatedDocumentRecord",
]
