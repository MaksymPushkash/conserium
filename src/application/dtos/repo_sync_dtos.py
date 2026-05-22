from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True, slots=True)
class RepoSyncDTO:
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
class RepoSyncListDTO:
    items: list[RepoSyncDTO]


@dataclass(frozen=True, slots=True)
class CreateRepoSyncDTO:
    user_id: UUID
    collection_id: UUID
    repo_url: str
    branch: str = "main"
    include_paths: list[str] | None = None
    exclude_paths: list[str] | None = None


@dataclass(frozen=True, slots=True)
class RunRepoSyncDTO:
    user_id: UUID
    repo_sync_id: UUID
    max_files: int = 50


@dataclass(frozen=True, slots=True)
class RepoSyncRunResultDTO:
    repo_sync: RepoSyncDTO
    created: int
    updated: int
    skipped: int
    deleted: int
    warnings: list[str]


@dataclass(frozen=True, slots=True)
class RepoSyncItemDTO:
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
class RepoSyncOutboxDTO:
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
class MarkdownRepoFileDTO:
    path: str
    sha: str
    content: str
    html_url: str


@dataclass(frozen=True, slots=True)
class MarkdownRepoFetchResultDTO:
    files: list[MarkdownRepoFileDTO]
    warnings: list[str]
