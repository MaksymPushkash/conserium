from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from src.application.dtos.document_dtos import DocumentDTO
from src.domain.value_objects.document_type import DocumentType


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


@dataclass(frozen=True, slots=True)
class ExternalIngestResultDTO:
    intake_item: ExternalIntakeItemDTO
    document: DocumentDTO | None
