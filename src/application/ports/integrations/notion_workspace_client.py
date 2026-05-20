from abc import ABC, abstractmethod

from src.application.dtos.external_connection_dtos import NotionPageDTO


class INotionWorkspaceClient(ABC):
    @abstractmethod
    async def search_pages(self, *, access_token: str, query: str | None, limit: int) -> list[NotionPageDTO]: ...
