from typing import Protocol

from src.integrations.schemas import (
    FetchedWebResource,
    NotionOAuthToken,
    NotionPageContentDTO,
    NotionPageResponse,
)
from src.repo_syncs.schemas import MarkdownRepoFetchResultDTO


class GitHubRepositoryClientProtocol(Protocol):
    async def fetch_markdown_files(
        self,
        *,
        owner: str,
        repo: str,
        branch: str,
        max_files: int,
    ) -> MarkdownRepoFetchResultDTO: ...


class NotionExportClientProtocol(Protocol):
    async def create_markdown_page(
        self,
        *,
        title: str,
        markdown: str,
        parent_page_id: str | None = None,
        access_token: str | None = None,
    ) -> tuple[str, str | None]: ...


class NotionOAuthClientProtocol(Protocol):
    def authorization_url(self, *, redirect_uri: str, state: str) -> str: ...

    async def exchange_code(self, *, code: str, redirect_uri: str) -> NotionOAuthToken: ...


class NotionWorkspaceClientProtocol(Protocol):
    async def search_pages(self, *, access_token: str, query: str | None, limit: int) -> list[NotionPageResponse]: ...

    async def get_page_markdown(self, *, access_token: str, page_id: str) -> NotionPageContentDTO: ...


class WebResourceFetcherProtocol(Protocol):
    async def fetch(self, url: str) -> FetchedWebResource | None: ...
