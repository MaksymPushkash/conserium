from abc import ABC, abstractmethod
from typing import Any
from uuid import UUID

from src.application.dtos.external_connection_dtos import ExternalConnectionDTO


class IExternalConnectionRepository(ABC):
    @abstractmethod
    async def get_by_provider(self, *, user_id: UUID, provider: str) -> ExternalConnectionDTO | None: ...

    @abstractmethod
    async def upsert(
        self,
        *,
        user_id: UUID,
        provider: str,
        workspace_id: str | None,
        workspace_name: str | None,
        access_token_encrypted: str,
        bot_id: str | None,
        owner: dict[str, Any] | None,
    ) -> ExternalConnectionDTO: ...

    @abstractmethod
    async def update_settings(
        self,
        *,
        user_id: UUID,
        provider: str,
        default_parent_page_id: str | None,
        default_parent_page_title: str | None,
    ) -> ExternalConnectionDTO | None: ...

    @abstractmethod
    async def delete_by_provider(self, *, user_id: UUID, provider: str) -> bool: ...
