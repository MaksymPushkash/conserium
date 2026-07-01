from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import UUID

from src.billing.service import billing
from src.documents.types import DocumentType
from src.kit.exceptions import ResourceNotFoundException
from src.models.document import DocumentModel
from src.repo_syncs.helpers import (
    document_title_from_path,
    filter_repo_files,
    normalize_max_files,
    sanitize_repo_sync_error,
    sanitized_repo_sync_exception,
    stale_repo_items,
    unique_repo_files,
)
from src.repo_syncs.schemas import MarkdownRepoFile, RepoSyncItem, RepoSyncResult, RepoSyncRunResult

if TYPE_CHECKING:
    from src.documents.activity_repository import DocumentActivityRepository
    from src.documents.document_repository import DocumentRepository
    from src.postgres import AsyncSession
    from src.repo_syncs.github_repository_client import GitHubRepositoryClient
    from src.repo_syncs.repository import RepoSyncRepository
    from src.worker.dispatcher import TaskiqTaskDispatcher


logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class _SyncFileResult:
    state: str
    document: DocumentModel | None


class RepoSyncRunner:
    def __init__(
        self,
        session: AsyncSession,
        document_repo: DocumentRepository,
        document_activity_repo: DocumentActivityRepository,
        repo_sync_repo: RepoSyncRepository,
        github_client: GitHubRepositoryClient,
        task_dispatcher: TaskiqTaskDispatcher,
    ) -> None:
        self._session = session
        self._document_repo = document_repo
        self._document_activity_repo = document_activity_repo
        self._repo_sync_repo = repo_sync_repo
        self._github_client = github_client
        self._task_dispatcher = task_dispatcher

    async def __call__(self, *, user_id: UUID, repo_sync_id: UUID, max_files: int) -> RepoSyncRunResult:
        max_files = normalize_max_files(max_files)
        repo_sync = await self._load_user_repo_sync(user_id, repo_sync_id)
        await self._set_repo_sync_state(repo_sync.id, status="running")
        try:
            fetch_result = await self._github_client.fetch_markdown_files(
                owner=repo_sync.owner,
                repo=repo_sync.repo,
                branch=repo_sync.branch,
                max_files=max_files,
            )
            filtered_files = filter_repo_files(
                fetch_result.files,
                include_paths=repo_sync.include_paths,
                exclude_paths=repo_sync.exclude_paths,
            )
            repo_sync, created, updated, skipped, deleted = await self._sync_files(repo_sync, filtered_files)
            if created or updated:
                await self._request_outbox_drain(repo_sync.id)
            else:
                repo_sync = await self._set_repo_sync_state(
                    repo_sync.id,
                    status="completed",
                    last_error=None,
                    last_synced_at=datetime.now(UTC),
                )
        except Exception as exc:
            message = sanitize_repo_sync_error(exc)
            await self._mark_repo_sync_failed(repo_sync.id, message)
            raise sanitized_repo_sync_exception(exc, message) from exc

        return RepoSyncRunResult(
            repo_sync=repo_sync,
            created=created,
            updated=updated,
            skipped=skipped,
            deleted=deleted,
            warnings=fetch_result.warnings,
        )

    async def _sync_files(
        self,
        repo_sync: RepoSyncResult,
        files: list[MarkdownRepoFile],
    ) -> tuple[RepoSyncResult, int, int, int, int]:
        now = datetime.now(UTC)
        created = 0
        updated = 0
        skipped = 0
        deleted = 0

        existing_items = await self._repo_sync_repo.list_items(repo_sync.id)
        current_paths = {file.path for file in files}
        for file in unique_repo_files(files):
            result = await self._sync_file(repo_sync, file, now)
            if result.state == "created":
                created += 1
                await self._create_document_outbox(repo_sync.id, result.document)
            elif result.state == "updated":
                updated += 1
                await self._create_document_outbox(repo_sync.id, result.document)
            else:
                skipped += 1

        for item in stale_repo_items(existing_items, current_paths):
            await self._repo_sync_repo.delete_item(item.id)
            await self._document_repo.delete(item.document_id)
            deleted += 1

        repo_sync = await self._repo_sync_repo.update_state(
            repo_sync_id=repo_sync.id,
            status="queueing",
            last_error=None,
        )
        await self._session.commit()

        return repo_sync, created, updated, skipped, deleted

    async def _create_document_outbox(self, repo_sync_id: UUID, document: DocumentModel | None) -> None:
        if document is None:
            return
        await self._repo_sync_repo.create_outbox(
            repo_sync_id=repo_sync_id,
            document_id=document.id,
            task_name="process_document",
        )

    async def _request_outbox_drain(self, repo_sync_id: UUID) -> None:
        try:
            await self._task_dispatcher.dispatch_repo_sync_outbox()
        except Exception as exc:
            logger.warning(
                "repo_sync_outbox_drain_enqueue_failed",
                extra={
                    "repo_sync_id": str(repo_sync_id),
                    "error_type": type(exc).__name__,
                    "sanitized_error": sanitize_repo_sync_error(exc),
                },
            )

    async def _load_user_repo_sync(self, user_id: UUID, repo_sync_id: UUID) -> RepoSyncResult:
        repo_sync = await self._repo_sync_repo.get_by_id(repo_sync_id)
        if repo_sync is None or repo_sync.user_id != user_id:
            raise ResourceNotFoundException("repo sync not found")
        return repo_sync

    async def _set_repo_sync_state(
        self,
        repo_sync_id: UUID,
        *,
        status: str,
        last_error: str | None = None,
        last_synced_at: datetime | None = None,
    ) -> RepoSyncResult:
        repo_sync = await self._repo_sync_repo.update_state(
            repo_sync_id=repo_sync_id,
            status=status,
            last_error=last_error,
            last_synced_at=last_synced_at,
        )
        await self._session.commit()
        return repo_sync

    async def _mark_repo_sync_failed(self, repo_sync_id: UUID, message: str) -> None:
        try:
            await self._set_repo_sync_state(repo_sync_id, status="failed", last_error=message)
        except Exception as exc:
            logger.exception(
                "repo_sync_failed_state_persistence_failed",
                extra={
                    "repo_sync_id": str(repo_sync_id),
                    "error_type": type(exc).__name__,
                    "sanitized_error": message,
                },
            )

    async def _sync_file(
        self,
        repo_sync: RepoSyncResult,
        file: MarkdownRepoFile,
        synced_at: datetime,
    ) -> _SyncFileResult:
        item = await self._repo_sync_repo.get_item_by_path(repo_sync_id=repo_sync.id, path=file.path)
        if item is not None and item.sha == file.sha:
            return _SyncFileResult(state="skipped", document=None)

        if item is None:
            await billing.ensure_can_create_document(self._session, user_id=repo_sync.user_id)
            document = self._create_document(repo_sync, file)
            await self._document_repo.create(document)
            await self._document_activity_repo.record_event(
                user_id=repo_sync.user_id,
                document_id=document.id,
                event_type="created",
            )
            state = "created"
        else:
            document = await self._load_item_document(item)
            document.rename(document_title_from_path(file.path))
            document.update_content(
                raw_content=file.content,
                word_count=len(file.content.split()),
                language=None,
            )
            await self._document_repo.update(document)
            state = "updated"

        await self._repo_sync_repo.upsert_item(
            repo_sync_id=repo_sync.id,
            path=file.path,
            sha=file.sha,
            document_id=document.id,
            source_url=file.html_url,
            synced_at=synced_at,
        )
        return _SyncFileResult(state=state, document=document)

    async def _load_item_document(self, item: RepoSyncItem) -> DocumentModel:
        document = await self._document_repo.get_by_id(item.document_id)
        if document is None:
            raise ResourceNotFoundException("synced document not found")
        return document

    def _create_document(self, repo_sync: RepoSyncResult, file: MarkdownRepoFile) -> DocumentModel:
        return DocumentModel.create(
            id=uuid.uuid4(),
            user_id=repo_sync.user_id,
            collection_id=repo_sync.collection_id,
            title=document_title_from_path(file.path),
            type=DocumentType.MARKDOWN,
            source_url=file.html_url,
            raw_content=file.content,
            file_size_bytes=len(file.content.encode()),
            word_count=len(file.content.split()),
        )


__all__ = ["RepoSyncRunner"]
