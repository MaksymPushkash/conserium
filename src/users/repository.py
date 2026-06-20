from __future__ import annotations

from typing import TYPE_CHECKING, Self

from sqlalchemy import delete, exists, select

from src.models.user import UserModel

if TYPE_CHECKING:
    from uuid import UUID

    from sqlalchemy.ext.asyncio import AsyncSession


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @classmethod
    def from_session(cls, session: AsyncSession) -> Self:
        return cls(session)

    async def get_by_id(self, user_id: UUID) -> UserModel | None:
        result = await self._session.execute(select(UserModel).where(UserModel.id == user_id))
        return result.scalar_one_or_none()

    async def get_by_email(self, email: str) -> UserModel | None:
        result = await self._session.execute(select(UserModel).where(UserModel.email == email))
        return result.scalar_one_or_none()

    async def exists_by_email(self, email: str) -> bool:
        result = await self._session.execute(select(exists().where(UserModel.email == email)))
        return result.scalar_one()

    async def create(self, user: UserModel) -> None:
        self._session.add(user)

    async def update(self, user: UserModel) -> None:
        self._session.add(user)

    async def delete(self, user_id: UUID) -> None:
        await self._session.execute(delete(UserModel).where(UserModel.id == user_id))

__all__ = ["UserRepository"]
