from dataclasses import dataclass
from typing import final
from uuid import UUID

from src.application.ports.persistence.unit_of_work import IUnitOfWork
from src.domain.entities.user_entity import UserEntity
from src.domain.exceptions import ResourceNotFoundException


@final
@dataclass(frozen=True, slots=True)
class UpdateUserPreferencesDTO:
    user_id: UUID
    preferences: dict[str, object]


class UpdateUserPreferencesUseCase:
    def __init__(self, uow: IUnitOfWork) -> None:
        self._uow = uow

    async def __call__(self, dto: UpdateUserPreferencesDTO) -> UserEntity:
        async with self._uow:
            user = await self._uow.user_repo.get_by_id(dto.user_id)
            if user is None:
                raise ResourceNotFoundException("user not found")
            user.update_preferences(dto.preferences)
            await self._uow.user_repo.update(user)
            await self._uow.commit()
            return user
