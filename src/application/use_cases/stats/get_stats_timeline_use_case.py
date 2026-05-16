from uuid import UUID

from src.application.dtos.stats_dtos import StatsTimelineBucketDTO, StatsTimelineDTO
from src.application.ports.persistence.unit_of_work import IUnitOfWork


class GetStatsTimelineUseCase:
    def __init__(self, uow: IUnitOfWork) -> None:
        self._uow = uow

    async def __call__(self, user_id: UUID, *, months: int = 6) -> StatsTimelineDTO:
        async with self._uow:
            buckets = await self._uow.stats_repo.get_learning_timeline(user_id=user_id, months=months)

        return StatsTimelineDTO(
            items=[
                StatsTimelineBucketDTO(
                    month=bucket.month,
                    saved_documents=bucket.saved_documents,
                    active_documents=bucket.active_documents,
                    query_count=bucket.query_count,
                    citation_count=bucket.citation_count,
                )
                for bucket in buckets
            ],
            months=months,
        )
