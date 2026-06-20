from __future__ import annotations

from typing import TYPE_CHECKING

from src.kit.exceptions import ResourceNotFoundException
from src.users.repository import UserRepository
from src.users.schemas import UserPreferencesResponse, UserResponse

if TYPE_CHECKING:
    from uuid import UUID

    from src.models.user import UserModel
    from src.postgres import AsyncSession


class UserService:
    def response(self, user: UserModel) -> UserResponse:
        return UserResponse(
            id=user.id,
            email=user.email,
            display_name=user.display_name,
            is_active=user.is_active,
            preferences=self.preferences_response(user.preferences),
            created_at=user.created_at,
            updated_at=user.updated_at,
        )

    def preferences_response(self, preferences: dict[str, object]) -> UserPreferencesResponse:
        return UserPreferencesResponse.model_validate(preferences or {})

    async def update_preferences(
        self,
        session: AsyncSession,
        *,
        user_id: UUID,
        preferences: dict[str, object],
    ) -> UserPreferencesResponse:
        repository = UserRepository.from_session(session)
        user = await repository.get_by_id(user_id)
        if user is None:
            raise ResourceNotFoundException("user not found")
        user.update_preferences(preferences)
        await repository.update(user)
        return self.preferences_response(user.preferences)

    async def delete(self, session: AsyncSession, *, user_id: UUID) -> None:
        repository = UserRepository.from_session(session)
        user = await repository.get_by_id(user_id)
        if user is None:
            raise ResourceNotFoundException("user not found")
        await repository.delete(user_id)


users = UserService()

__all__ = ["UserService", "users"]
