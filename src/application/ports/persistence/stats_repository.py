from abc import ABC, abstractmethod
from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class StatsTimelineBucket:
    month: str
    saved_documents: int
    active_documents: int
    query_count: int
    citation_count: int


@dataclass(frozen=True, slots=True)
class StatsOverviewRecord:
    total_documents: int
    ready_documents: int
    processing_documents: int
    failed_documents: int
    hot_documents: int
    cold_documents: int
    forgotten_documents: int
    active_documents: int
    query_count: int
    citation_count: int


class IStatsRepository(ABC):
    @abstractmethod
    async def get_overview(self, *, user_id: UUID) -> StatsOverviewRecord: ...

    @abstractmethod
    async def get_learning_timeline(self, *, user_id: UUID, months: int) -> list[StatsTimelineBucket]: ...
