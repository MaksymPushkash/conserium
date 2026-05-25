from uuid import UUID

from src.application.dtos.topic_dtos import TopicListDTO
from src.application.ports.persistence.unit_of_work import IUnitOfWork
from src.application.use_cases.topics.topic_mapping import topic_to_dto


class ListTopicsUseCase:
    def __init__(self, uow: IUnitOfWork) -> None:
        self._uow = uow

    async def __call__(self, *, user_id: UUID, limit: int = 50, offset: int = 0) -> TopicListDTO:
        async with self._uow:
            records = await self._uow.topic_repo.list_by_user_id(user_id, limit=limit, offset=offset)
            total = await self._uow.topic_repo.count_by_user_id(user_id)

        return TopicListDTO(
            items=[topic_to_dto(record) for record in records],
            total=total,
            limit=limit,
            offset=offset,
        )
