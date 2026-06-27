from __future__ import annotations

import fnmatch
import re
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import TYPE_CHECKING

from src.kit.exceptions import DomainException, IntegrationRequestException, ValidationException
from src.repo_syncs.schemas import MarkdownRepoFile, RepoSyncItem

if TYPE_CHECKING:
    from uuid import UUID

_REPO_URL_PATTERN = re.compile(r"^(?:https://github\.com/|git@github\.com:)(?P<owner>[^/\s]+)/(?P<repo>[^/\s]+?)(?:\.git)?/?$")
MIN_SYNC_FILES = 1
MAX_SYNC_FILES = 250
DEFAULT_INCLUDE_PATHS = ("README.md", "docs/**/*.md", "**/*.md")
DEFAULT_EXCLUDE_PATHS = ("node_modules/**", ".git/**", "dist/**")

type RepoPathItem = RepoSyncItem | MarkdownRepoFile


@dataclass(frozen=True, slots=True)
class GitHubRepoRef:
    owner: str
    repo: str


def parse_github_repo_url(repo_url: str) -> GitHubRepoRef:
    match = _REPO_URL_PATTERN.match(repo_url.strip())
    if match is None:
        raise ValidationException("repo_url must be a GitHub repository URL")
    return GitHubRepoRef(owner=match.group("owner"), repo=match.group("repo"))


def document_title_from_path(path: str) -> str:
    stem = PurePosixPath(path).stem.strip()
    return stem.replace("-", " ").replace("_", " ") or path


def stale_repo_items[T: RepoPathItem](items: list[T], current_paths: set[str]) -> list[T]:
    return [item for item in items if item.path not in current_paths]


def normalize_max_files(max_files: int) -> int:
    if max_files < MIN_SYNC_FILES:
        raise ValidationException("max_files must be at least 1")
    return min(max_files, MAX_SYNC_FILES)


def unique_repo_files[T: RepoPathItem](files: list[T]) -> list[T]:
    unique: dict[str, T] = {}
    for file in files:
        unique[file.path] = file
    return list(unique.values())


def normalize_repo_path_patterns(patterns: list[str] | None, default: tuple[str, ...]) -> list[str]:
    if patterns is None:
        return list(default)
    cleaned = [pattern.strip() for pattern in patterns if pattern.strip()]
    return cleaned or list(default)


def filter_repo_files[T: RepoPathItem](
    files: list[T],
    *,
    include_paths: list[str],
    exclude_paths: list[str],
) -> list[T]:
    return [
        file
        for file in files
        if _path_matches_any(file.path, include_paths) and not _path_matches_any(file.path, exclude_paths)
    ]


def sanitize_repo_sync_error(exc: Exception) -> str:
    message = str(exc).strip()
    lowered = message.lower()
    if "rate limit" in lowered or "403" in lowered:
        return "GitHub rate limit or access policy blocked this sync."
    if "401" in lowered or "unauthorized" in lowered:
        return "GitHub authentication failed for this sync."
    if "404" in lowered or "not found" in lowered:
        return "GitHub repository or branch was not found."
    if isinstance(exc, ValidationException):
        return message
    if isinstance(exc, IntegrationRequestException) and message:
        return message
    return "GitHub sync failed. Check repository access, branch, and Markdown file availability."


def sanitize_outbox_error(exc: Exception) -> str:
    message = str(exc).strip()
    return message[:500] if message else type(exc).__name__


def sanitized_repo_sync_exception(exc: Exception, message: str) -> DomainException:
    if isinstance(exc, ValidationException):
        return ValidationException(message)
    return IntegrationRequestException(message)


def repo_sync_outbox_task_id(outbox_id: UUID) -> str:
    return f"repo-sync-outbox-{outbox_id}"


def _path_matches_any(path: str, patterns: list[str]) -> bool:
    return any(PurePosixPath(path).match(pattern) or fnmatch.fnmatchcase(path, pattern) for pattern in patterns)


__all__ = [
    "DEFAULT_EXCLUDE_PATHS",
    "DEFAULT_INCLUDE_PATHS",
    "MAX_SYNC_FILES",
    "MIN_SYNC_FILES",
    "GitHubRepoRef",
    "RepoPathItem",
    "document_title_from_path",
    "filter_repo_files",
    "normalize_max_files",
    "normalize_repo_path_patterns",
    "parse_github_repo_url",
    "repo_sync_outbox_task_id",
    "sanitize_outbox_error",
    "sanitize_repo_sync_error",
    "sanitized_repo_sync_exception",
    "stale_repo_items",
    "unique_repo_files",
]
