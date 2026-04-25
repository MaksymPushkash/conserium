from abc import ABC, abstractmethod
from uuid import UUID

from src.domain.entities.user_entity import UserEntity


class IUserRepository(ABC):
    @abstractmethod
    async def get_by_id(self, user_id: UUID) -> UserEntity | None: ...
 
    @abstractmethod
    async def get_by_email(self, email: str) -> UserEntity | None: ...
 
    @abstractmethod
    async def create(self, user: UserEntity) -> None: ...
 
    @abstractmethod
    async def update(self, user: UserEntity) -> None: ...
 
    @abstractmethod
    async def exists_by_email(self, email: str) -> bool: ...
 