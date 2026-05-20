from __future__ import annotations

import asyncio
from urllib.parse import quote

import httpx

from src.application.dtos.repo_sync_dtos import MarkdownRepoFetchResultDTO, MarkdownRepoFileDTO
from src.application.ports.integrations.github_repository_client import IGitHubRepositoryClient
from src.core.config import settings
from src.domain.exceptions import IntegrationRequestException, ValidationException

_GITHUB_API_BASE_URL = "https://api.github.com"
_RAW_BASE_URL = "https://raw.githubusercontent.com"
_HTML_BASE_URL = "https://github.com"
_MARKDOWN_SUFFIXES = (".md", ".markdown")
_MAX_FILE_BYTES = 1_000_000


class GitHubRepositoryClient(IGitHubRepositoryClient):
    def __init__(self, token: str | None = None) -> None:
        self._token = token if token is not None else settings.GITHUB_TOKEN

    async def fetch_markdown_files(
        self,
        *,
        owner: str,
        repo: str,
        branch: str,
        max_files: int,
    ) -> MarkdownRepoFetchResultDTO:
        async with httpx.AsyncClient(timeout=20) as client:
            tree = await self._fetch_tree(client, owner=owner, repo=repo, branch=branch)
            candidates = [
                item
                for item in tree
                if item.get("type") == "blob" and _is_markdown_path(str(item.get("path", "")))
            ][:max_files]
            semaphore = asyncio.Semaphore(6)
            results = await asyncio.gather(
                *(self._fetch_markdown_file(client, owner=owner, repo=repo, branch=branch, item=item, semaphore=semaphore) for item in candidates),
                return_exceptions=True,
            )
            files: list[MarkdownRepoFileDTO] = []
            failed = 0
            skipped_large = 0
            for result in results:
                if isinstance(result, _SkippedLargeFile):
                    skipped_large += 1
                elif isinstance(result, BaseException):
                    failed += 1
                else:
                    files.append(result)

            warnings: list[str] = []
            if failed:
                warnings.append(f"Skipped {failed} Markdown file{'s' if failed != 1 else ''} that could not be fetched.")
            if skipped_large:
                warnings.append(f"Skipped {skipped_large} Markdown file{'s' if skipped_large != 1 else ''} larger than 1 MB.")
            return MarkdownRepoFetchResultDTO(files=files, warnings=warnings)

    async def _fetch_markdown_file(
        self,
        client: httpx.AsyncClient,
        *,
        owner: str,
        repo: str,
        branch: str,
        item: dict[str, object],
        semaphore: asyncio.Semaphore,
    ) -> MarkdownRepoFileDTO | _SkippedLargeFile:
        path = str(item["path"])
        if _tree_item_size(item) > _MAX_FILE_BYTES:
            return _SkippedLargeFile()
        async with semaphore:
            content = await self._fetch_raw_file(client, owner=owner, repo=repo, branch=branch, path=path)
        return MarkdownRepoFileDTO(
            path=path,
            sha=str(item["sha"]),
            content=content,
            html_url=f"{_HTML_BASE_URL}/{owner}/{repo}/blob/{quote(branch)}/{quote(path)}",
        )

    async def _fetch_tree(
        self,
        client: httpx.AsyncClient,
        *,
        owner: str,
        repo: str,
        branch: str,
    ) -> list[dict[str, object]]:
        headers = {"Accept": "application/vnd.github+json", **self._auth_header()}
        response = await client.get(
            f"{_GITHUB_API_BASE_URL}/repos/{owner}/{repo}/git/trees/{quote(branch)}",
            params={"recursive": "1"},
            headers=headers,
        )
        if response.status_code == 404:
            raise ValidationException("GitHub repository or branch was not found")
        raise_github_error(response)
        payload = response.json()
        if payload.get("truncated") is True:
            raise IntegrationRequestException("GitHub repository tree is too large to sync safely.")
        tree = payload.get("tree", [])
        if not isinstance(tree, list):
            return []
        return [item for item in tree if isinstance(item, dict)]

    async def _fetch_raw_file(
        self,
        client: httpx.AsyncClient,
        *,
        owner: str,
        repo: str,
        branch: str,
        path: str,
    ) -> str:
        response = await client.get(
            f"{_RAW_BASE_URL}/{owner}/{repo}/{quote(branch)}/{quote(path)}",
            headers=self._auth_header(),
        )
        raise_github_error(response)
        return response.text

    def _auth_header(self) -> dict[str, str]:
        if not self._token:
            return {}
        return {"Authorization": f"Bearer {self._token}"}


def _is_markdown_path(path: str) -> bool:
    return path.lower().endswith(_MARKDOWN_SUFFIXES)


def _tree_item_size(item: dict[str, object]) -> int:
    size = item.get("size")
    if isinstance(size, int):
        return size
    if isinstance(size, str) and size.isdigit():
        return int(size)
    return 0


class _SkippedLargeFile:
    pass


def raise_github_error(response: httpx.Response) -> None:
    if response.status_code < 400:
        return
    if response.status_code in {401, 403}:
        raise IntegrationRequestException("GitHub access was rejected or rate limited")
    if response.status_code == 404:
        raise ValidationException("GitHub repository or branch was not found")
    raise IntegrationRequestException("GitHub request failed")
