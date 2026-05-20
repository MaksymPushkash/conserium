from abc import ABC, abstractmethod


class INotionExportClient(ABC):
    @abstractmethod
    async def create_markdown_page(
        self,
        *,
        title: str,
        markdown: str,
        parent_page_id: str | None = None,
        access_token: str | None = None,
    ) -> tuple[str, str | None]: ...
