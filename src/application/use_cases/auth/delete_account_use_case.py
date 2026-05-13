from uuid import UUID

from src.application.ports.persistence.unit_of_work import IUnitOfWork
from src.domain.exceptions import ResourceNotFoundException


class DeleteAccountUseCase:
    def __init__(self, uow: IUnitOfWork) -> None:
        self._uow = uow

    async def __call__(self, user_id: UUID) -> None:
        async with self._uow:
            user = await self._uow.user_repo.get_by_id(user_id)
            if user is None:
                raise ResourceNotFoundException("user not found")
            await self._uow.user_repo.delete(user_id)
            await self._uow.commit()
