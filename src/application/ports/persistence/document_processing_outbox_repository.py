from abc import ABC, abstractmethod
from datetime import datetime
from uuid import UUID

from src.application.dtos.document_processing_outbox_dtos import DocumentProcessingOutboxDTO


class IDocumentProcessingOutboxRepository(ABC):
    @abstractmethod
    async def create_outbox(self, *, document_id: UUID, task_name: str) -> DocumentProcessingOutboxDTO: ...

    @abstractmethod
    async def claim_batch(
        self,
        *,
        limit: int,
        locked_at: datetime,
        stale_before: datetime,
        max_attempts: int,
    ) -> list[DocumentProcessingOutboxDTO]: ...

    @abstractmethod
    async def mark_dispatched(self, outbox_id: UUID, dispatched_at: datetime) -> DocumentProcessingOutboxDTO: ...

    @abstractmethod
    async def mark_failed(self, outbox_id: UUID, *, last_error: str, retryable: bool) -> DocumentProcessingOutboxDTO: ...
