from abc import ABC, abstractmethod
from datetime import datetime
from uuid import UUID

from src.application.dtos.collection_share_dtos import CollectionShareDTO, PublicCollectionDTO


class ICollectionShareRepository(ABC):
    @abstractmethod
    async def get_active_by_collection_id(self, *, user_id: UUID, collection_id: UUID) -> CollectionShareDTO | None: ...

    @abstractmethod
    async def get_active_by_slug(self, slug: str) -> CollectionShareDTO | None: ...

    @abstractmethod
    async def create(
        self,
        *,
        id: UUID,
        collection_id: UUID,
        user_id: UUID,
        slug: str,
        include_summaries: bool,
        include_notes: bool,
    ) -> CollectionShareDTO: ...

    @abstractmethod
    async def revoke_by_collection_id(self, *, user_id: UUID, collection_id: UUID, revoked_at: datetime) -> bool: ...

    @abstractmethod
    async def get_public_collection(self, slug: str) -> PublicCollectionDTO | None: ...
