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


class IStatsRepository(ABC):
    @abstractmethod
    async def get_learning_timeline(self, *, user_id: UUID, months: int) -> list[StatsTimelineBucket]: ...
