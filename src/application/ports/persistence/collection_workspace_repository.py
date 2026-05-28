from abc import ABC, abstractmethod
from dataclasses import dataclass
from uuid import UUID

from src.application.dtos.compare_dtos import CompareResultDTO
from src.application.ports.persistence.draft_repository import DraftRecord
from src.application.ports.persistence.search_query_repository import SearchQuerySummaryRecord


@dataclass(frozen=True, slots=True)
class CollectionWorkspaceRecentActivity:
    questions: list[SearchQuerySummaryRecord]
    drafts: list[DraftRecord]
    comparisons: list[CompareResultDTO]


class ICollectionWorkspaceRepository(ABC):
    @abstractmethod
    async def get_recent_activity(
        self,
        *,
        user_id: UUID,
        collection_id: UUID,
        limit: int,
    ) -> CollectionWorkspaceRecentActivity: ...
