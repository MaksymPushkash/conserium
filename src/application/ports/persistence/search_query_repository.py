from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datetime import datetime
    from uuid import UUID

    from src.application.dtos.evaluation_dtos import QueryEvaluationRecordDTO


@dataclass(frozen=True, slots=True)
class SearchQuerySummaryRecord:
    query_text: str
    answer_text: str | None
    result_count: int
    created_at: datetime


class ISearchQueryRepository(ABC):
    @abstractmethod
    async def record_query(self, record: QueryEvaluationRecordDTO) -> None:
        """Persist query execution metadata and evaluation scores."""

    @abstractmethod
    async def list_recent_by_collection(
        self,
        *,
        user_id: UUID,
        collection_id: UUID,
        limit: int,
    ) -> list[SearchQuerySummaryRecord]: ...

    @abstractmethod
    async def list_recent_by_document(
        self,
        *,
        user_id: UUID,
        document_id: UUID,
        limit: int,
    ) -> list[SearchQuerySummaryRecord]: ...
