from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from uuid import UUID

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


class IDocumentActivityRepository(ABC):
    @abstractmethod
    async def record_event(self, *, user_id: UUID, document_id: UUID, event_type: DocumentActivityEventType) -> None: ...

    @abstractmethod
    async def summarize_by_document_ids(
        self,
        *,
        user_id: UUID,
        document_ids: list[UUID],
    ) -> dict[UUID, DocumentActivitySummary]: ...

    @abstractmethod
    async def summarize_user_overview(self, *, user_id: UUID) -> DocumentActivityOverview: ...
