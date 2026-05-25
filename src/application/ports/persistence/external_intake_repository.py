from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from src.domain.value_objects.document_type import DocumentType


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


class IExternalIntakeRepository(ABC):
    @abstractmethod
    async def create(self, record: ExternalIntakeItemRecord) -> ExternalIntakeItemRecord: ...

    @abstractmethod
    async def get_by_idempotency_key(
        self,
        *,
        user_id: UUID,
        provider: str,
        idempotency_key: str,
    ) -> ExternalIntakeItemRecord | None: ...

    @abstractmethod
    async def mark_queued(
        self,
        *,
        intake_item_id: UUID,
        document_id: UUID,
    ) -> ExternalIntakeItemRecord: ...

    @abstractmethod
    async def mark_failed(
        self,
        *,
        intake_item_id: UUID,
        error_reason: str,
    ) -> ExternalIntakeItemRecord: ...
