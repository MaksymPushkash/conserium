from abc import ABC, abstractmethod

from src.application.interfaces.user_repository import IUserRepository


class IUnitOfWork(ABC):
 
    user_repo: IUserRepository
 
    @abstractmethod
    async def __aenter__(self) -> "IUnitOfWork": ...
 
    @abstractmethod
    async def __aexit__(self, exc_type, exc, tb) -> None: ...
 
    @abstractmethod
    async def commit(self) -> None: ...
 
    @abstractmethod
    async def rollback(self) -> None: ...
    