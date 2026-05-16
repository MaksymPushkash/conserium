from uuid import UUID

from src.application.dtos.stats_dtos import StatsOverviewDTO
from src.application.ports.persistence.unit_of_work import IUnitOfWork
from src.domain.value_objects.document_status import DocumentStatus


class GetStatsOverviewUseCase:
    def __init__(self, uow: IUnitOfWork) -> None:
        self._uow = uow

    async def __call__(self, user_id: UUID) -> StatsOverviewDTO:
        async with self._uow:
            total_documents = await self._uow.document_repo.count_by_user_id(user_id)
            ready_documents = await self._uow.document_repo.count_by_user_id(user_id, status=DocumentStatus.READY)
            failed_documents = await self._uow.document_repo.count_by_user_id(user_id, status=DocumentStatus.FAILED)
            processing_documents = await self._count_processing_documents(user_id)
            activity = await self._uow.document_activity_repo.summarize_user_overview(user_id=user_id)

        return StatsOverviewDTO(
            total_documents=total_documents,
            ready_documents=ready_documents,
            processing_documents=processing_documents,
            failed_documents=failed_documents,
            hot_documents=activity.hot_documents,
            cold_documents=activity.cold_documents,
            forgotten_documents=activity.forgotten_documents,
            active_documents=activity.active_documents,
            query_count=activity.query_count,
            citation_count=activity.citation_count,
        )

    async def _count_processing_documents(self, user_id: UUID) -> int:
        counts = await self._count_statuses(
            user_id,
            (DocumentStatus.PENDING, DocumentStatus.QUEUED, DocumentStatus.PROCESSING),
        )
        return sum(counts)

    async def _count_statuses(self, user_id: UUID, statuses: tuple[DocumentStatus, ...]) -> list[int]:
        return [await self._uow.document_repo.count_by_user_id(user_id, status=status) for status in statuses]
