from abc import ABC, abstractmethod
from datetime import datetime
from uuid import UUID

from src.application.dtos.repo_sync_dtos import RepoSyncDTO, RepoSyncItemDTO, RepoSyncOutboxDTO


class IRepoSyncRepository(ABC):
    @abstractmethod
    async def list_by_user_id(self, user_id: UUID) -> list[RepoSyncDTO]: ...

    @abstractmethod
    async def list_due_for_sync(self, *, before: datetime, limit: int) -> list[RepoSyncDTO]: ...

    @abstractmethod
    async def get_by_id(self, repo_sync_id: UUID) -> RepoSyncDTO | None: ...

    @abstractmethod
    async def get_by_repo(
        self,
        *,
        user_id: UUID,
        owner: str,
        repo: str,
        branch: str,
    ) -> RepoSyncDTO | None: ...

    @abstractmethod
    async def create(
        self,
        *,
        id: UUID,
        user_id: UUID,
        collection_id: UUID,
        provider: str,
        owner: str,
        repo: str,
        branch: str,
        include_paths: list[str],
        exclude_paths: list[str],
    ) -> RepoSyncDTO: ...

    @abstractmethod
    async def update_filters(
        self,
        *,
        repo_sync_id: UUID,
        include_paths: list[str],
        exclude_paths: list[str],
    ) -> RepoSyncDTO: ...

    @abstractmethod
    async def update_state(
        self,
        *,
        repo_sync_id: UUID,
        status: str,
        last_error: str | None = None,
        last_synced_at: datetime | None = None,
    ) -> RepoSyncDTO: ...

    @abstractmethod
    async def list_items(self, repo_sync_id: UUID) -> list[RepoSyncItemDTO]: ...

    @abstractmethod
    async def get_item_by_path(self, *, repo_sync_id: UUID, path: str) -> RepoSyncItemDTO | None: ...

    @abstractmethod
    async def upsert_item(
        self,
        *,
        repo_sync_id: UUID,
        path: str,
        sha: str,
        document_id: UUID,
        source_url: str,
        synced_at: datetime,
    ) -> RepoSyncItemDTO: ...

    @abstractmethod
    async def delete_item(self, item_id: UUID) -> None: ...

    @abstractmethod
    async def create_outbox(
        self,
        *,
        repo_sync_id: UUID,
        document_id: UUID,
        task_name: str,
    ) -> RepoSyncOutboxDTO: ...

    @abstractmethod
    async def claim_outbox_batch(
        self,
        *,
        limit: int,
        locked_at: datetime,
        stale_before: datetime,
        max_attempts: int,
    ) -> list[RepoSyncOutboxDTO]: ...

    @abstractmethod
    async def mark_outbox_dispatched(self, outbox_id: UUID, dispatched_at: datetime) -> RepoSyncOutboxDTO: ...

    @abstractmethod
    async def mark_outbox_failed(
        self,
        outbox_id: UUID,
        *,
        last_error: str,
        retryable: bool,
    ) -> RepoSyncOutboxDTO: ...

    @abstractmethod
    async def has_active_outbox(self, repo_sync_id: UUID) -> bool: ...
