from uuid import UUID

from src.application.dtos.topic_dtos import TopicDTO, TopicListDTO
from src.application.ports.persistence.unit_of_work import IUnitOfWork


class ListTopicsUseCase:
    def __init__(self, uow: IUnitOfWork) -> None:
        self._uow = uow

    async def __call__(self, *, user_id: UUID, limit: int = 50, offset: int = 0) -> TopicListDTO:
        async with self._uow:
            records = await self._uow.topic_repo.list_by_user_id(user_id, limit=limit, offset=offset)
            total = await self._uow.topic_repo.count_by_user_id(user_id)

        return TopicListDTO(
            items=[
                TopicDTO(
                    name=record.name,
                    document_count=record.document_count,
                    last_document_at=record.last_document_at,
                )
                for record in records
            ],
            total=total,
            limit=limit,
            offset=offset,
        )
