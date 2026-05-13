from abc import ABC, abstractmethod
from uuid import UUID

from src.domain.entities.collection_entity import CollectionEntity


class ICollectionRepository(ABC):
    @abstractmethod
    async def get_by_id(self, collection_id: UUID) -> CollectionEntity | None: ...

    @abstractmethod
    async def get_by_user_id(self, user_id: UUID, *, limit: int = 100, offset: int = 0) -> list[CollectionEntity]: ...

    @abstractmethod
    async def create(self, collection: CollectionEntity) -> None: ...

    @abstractmethod
    async def update(self, collection: CollectionEntity) -> None: ...

    @abstractmethod
    async def delete(self, collection_id: UUID) -> None: ...

    @abstractmethod
    async def count_by_user_id(self, user_id: UUID) -> int: ...
