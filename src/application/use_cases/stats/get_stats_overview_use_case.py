from uuid import UUID

from src.application.dtos.stats_dtos import StatsOverviewDTO
from src.application.ports.persistence.unit_of_work import IUnitOfWork


class GetStatsOverviewUseCase:
    def __init__(self, uow: IUnitOfWork) -> None:
        self._uow = uow

    async def __call__(self, user_id: UUID) -> StatsOverviewDTO:
        async with self._uow:
            overview = await self._uow.stats_repo.get_overview(user_id=user_id)

        return StatsOverviewDTO(
            total_documents=overview.total_documents,
            ready_documents=overview.ready_documents,
            processing_documents=overview.processing_documents,
            failed_documents=overview.failed_documents,
            hot_documents=overview.hot_documents,
            cold_documents=overview.cold_documents,
            forgotten_documents=overview.forgotten_documents,
            active_documents=overview.active_documents,
            query_count=overview.query_count,
            citation_count=overview.citation_count,
        )
