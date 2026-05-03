from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.application.dtos.evaluation_dtos import QueryEvaluationRecordDTO


class ISearchQueryRepository(ABC):
    @abstractmethod
    async def record_query(self, record: QueryEvaluationRecordDTO) -> None:
        """Persist query execution metadata and evaluation scores."""
