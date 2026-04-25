'''
from abc import ABC, abstractmethod

from sqlalchemy.ext.asyncio import AsyncSession

from src.application.interfaces.user_repository import IUserRepository
from src.infrastructure.database.repositories.user_repository import SQLAlchemyUserRepository


class IUnitOfWork(ABC):

    user_repo: IUserRepository
    
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self.user_repo = SQLAlchemyUserRepository(session)

    @abstractmethod
    async def __aenter__(self) -> "IUnitOfWork":
        ...

    @abstractmethod
    async def __aexit__(self, exc_type, exc, tb) -> None:
        ...

    @abstractmethod
    async def commit(self) -> None:
        ...

    @abstractmethod
    async def rollback(self) -> None:
        ...
'''