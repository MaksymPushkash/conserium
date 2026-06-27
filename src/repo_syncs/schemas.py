from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime  # noqa: TC003
from uuid import UUID  # noqa: TC003

from pydantic import BaseModel, Field


@dataclass(frozen=True, slots=True)
class RepoSyncResult:
    id: UUID
    user_id: UUID
    collection_id: UUID
    provider: str
    owner: str
    repo: str
    branch: str
    include_paths: list[str]
    exclude_paths: list[str]
    status: str
    last_error: str | None
    last_synced_at: datetime | None
    created_at: datetime
    updated_at: datetime | None


@dataclass(frozen=True, slots=True)
class RepoSyncListResult:
    items: list[RepoSyncResult]


@dataclass(frozen=True, slots=True)
class RepoSyncRunResult:
    repo_sync: RepoSyncResult
    created: int
    updated: int
    skipped: int
    deleted: int
    warnings: list[str]


@dataclass(frozen=True, slots=True)
class RepoSyncItem:
    id: UUID
    repo_sync_id: UUID
    path: str
    sha: str
    document_id: UUID
    source_url: str
    last_synced_at: datetime
    created_at: datetime
    updated_at: datetime | None


@dataclass(frozen=True, slots=True)
class RepoSyncOutboxRecord:
    id: UUID
    repo_sync_id: UUID
    document_id: UUID
    task_name: str
    status: str
    attempts: int
    locked_at: datetime | None
    last_error: str | None
    dispatched_at: datetime | None
    created_at: datetime
    updated_at: datetime | None


@dataclass(frozen=True, slots=True)
class MarkdownRepoFile:
    path: str
    sha: str
    content: str
    html_url: str


@dataclass(frozen=True, slots=True)
class MarkdownRepoFetchResult:
    files: list[MarkdownRepoFile]
    warnings: list[str]


class CreateRepoSyncRequest(BaseModel):
    collection_id: UUID
    repo_url: str = Field(min_length=1, max_length=500)
    branch: str = Field(default="main", min_length=1, max_length=120)
    include_paths: list[str] | None = None
    exclude_paths: list[str] | None = None


class RunRepoSyncRequest(BaseModel):
    max_files: int = Field(default=50, ge=1, le=200)


class RepoSyncResponse(BaseModel):
    id: UUID
    collection_id: UUID
    provider: str
    owner: str
    repo: str
    branch: str
    include_paths: list[str]
    exclude_paths: list[str]
    status: str
    last_error: str | None
    last_synced_at: datetime | None
    created_at: datetime
    updated_at: datetime | None


class RepoSyncListResponse(BaseModel):
    items: list[RepoSyncResponse]


class RepoSyncRunResponse(BaseModel):
    repo_sync: RepoSyncResponse
    created: int
    updated: int
    skipped: int
    deleted: int
    warnings: list[str] = Field(default_factory=list)
