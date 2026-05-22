from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


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
