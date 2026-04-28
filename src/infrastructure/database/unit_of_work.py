from typing import TYPE_CHECKING

from sqlalchemy.ext.asyncio import AsyncSession

from src.application.interfaces.unit_of_work import IUnitOfWork
from src.infrastructure.database.repositories.user_repository import SQLAlchemyUserRepository

if TYPE_CHECKING:
    from src.application.interfaces.user_repository import IUserRepository


class SQLAlchemyUnitOfWork(IUnitOfWork):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self.user_repo: IUserRepository = SQLAlchemyUserRepository(session)
 
    async def __aenter__(self) -> "SQLAlchemyUnitOfWork":
        return self
 
    async def __aexit__(self, exc_type, exc, tb) -> None:
        if exc_type:
            await self.rollback()
 
    async def commit(self) -> None:
        await self._session.commit()
 
    async def rollback(self) -> None:
        await self._session.rollback()