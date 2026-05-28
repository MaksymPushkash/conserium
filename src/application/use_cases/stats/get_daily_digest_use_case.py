from uuid import UUID

from src.application.dtos.stats_dtos import DailyDigestDTO, DailyDigestItemDTO
from src.application.ports.persistence.unit_of_work import IUnitOfWork


class GetDailyDigestUseCase:
    def __init__(self, uow: IUnitOfWork) -> None:
        self._uow = uow

    async def __call__(self, user_id: UUID, *, limit: int = 3) -> DailyDigestDTO:
        async with self._uow:
            items = await self._uow.stats_repo.get_daily_digest_items(user_id=user_id, limit=limit)

        return DailyDigestDTO(
            items=[
                DailyDigestItemDTO(
                    document_id=item.document_id,
                    title=item.title,
                    summary=item.summary,
                    question=item.question,
                    reason=item.reason,
                    last_used_at=item.last_used_at,
                    days_since_activity=item.days_since_activity,
                )
                for item in items
            ]
        )
