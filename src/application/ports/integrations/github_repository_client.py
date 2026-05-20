from abc import ABC, abstractmethod

from src.application.dtos.repo_sync_dtos import MarkdownRepoFetchResultDTO


class IGitHubRepositoryClient(ABC):
    @abstractmethod
    async def fetch_markdown_files(
        self,
        *,
        owner: str,
        repo: str,
        branch: str,
        max_files: int,
    ) -> MarkdownRepoFetchResultDTO: ...
