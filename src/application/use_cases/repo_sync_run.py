from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import UUID

from src.application.dtos.repo_sync_dtos import RepoSyncDTO, RepoSyncRunResultDTO, RunRepoSyncDTO
from src.application.use_cases.repo_sync_helpers import (
    document_title_from_path,
    filter_repo_files,
    normalize_max_files,
    sanitize_repo_sync_error,
    sanitized_repo_sync_exception,
    stale_repo_items,
    unique_repo_files,
)
from src.domain.entities.document_entity import DocumentEntity
from src.domain.exceptions import ResourceNotFoundException
from src.domain.value_objects.document_type import DocumentType

if TYPE_CHECKING:
    from src.application.dtos.repo_sync_dtos import MarkdownRepoFileDTO, RepoSyncItemDTO
    from src.application.ports.ingestion.task_dispatcher import ITaskDispatcher
    from src.application.ports.integrations.github_repository_client import IGitHubRepositoryClient
    from src.application.ports.persistence.unit_of_work import IUnitOfWork


logger = logging.getLogger(__name__)


class RunRepoSyncUseCase:
    def __init__(
        self,
        uow: IUnitOfWork,
        github_client: IGitHubRepositoryClient,
        task_dispatcher: ITaskDispatcher,
    ) -> None:
        self._uow = uow
        self._github_client = github_client
        self._task_dispatcher = task_dispatcher

    async def __call__(self, dto: RunRepoSyncDTO) -> RepoSyncRunResultDTO:
        max_files = normalize_max_files(dto.max_files)
        repo_sync = await self._load_user_repo_sync(dto.user_id, dto.repo_sync_id)
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

        return RepoSyncRunResultDTO(
            repo_sync=repo_sync,
            created=created,
            updated=updated,
            skipped=skipped,
            deleted=deleted,
            warnings=fetch_result.warnings,
        )

    async def _sync_files(
        self,
        repo_sync: RepoSyncDTO,
        files: list[MarkdownRepoFileDTO],
    ) -> tuple[RepoSyncDTO, int, int, int, int]:
        now = datetime.now(UTC)
        created = 0
        updated = 0
        skipped = 0
        deleted = 0

        async with self._uow:
            existing_items = await self._uow.repo_sync_repo.list_items(repo_sync.id)
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
                await self._uow.repo_sync_repo.delete_item(item.id)
                await self._uow.document_repo.delete(item.document_id)
                deleted += 1

            repo_sync = await self._uow.repo_sync_repo.update_state(
                repo_sync_id=repo_sync.id,
                status="queueing",
                last_error=None,
            )
            await self._uow.commit()

        return repo_sync, created, updated, skipped, deleted

    async def _create_document_outbox(self, repo_sync_id: UUID, document: DocumentEntity | None) -> None:
        if document is None:
            return
        await self._uow.repo_sync_repo.create_outbox(
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

    async def _load_user_repo_sync(self, user_id: UUID, repo_sync_id: UUID) -> RepoSyncDTO:
        async with self._uow:
            repo_sync = await self._uow.repo_sync_repo.get_by_id(repo_sync_id)
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
    ) -> RepoSyncDTO:
        async with self._uow:
            repo_sync = await self._uow.repo_sync_repo.update_state(
                repo_sync_id=repo_sync_id,
                status=status,
                last_error=last_error,
                last_synced_at=last_synced_at,
            )
            await self._uow.commit()
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
        repo_sync: RepoSyncDTO,
        file: MarkdownRepoFileDTO,
        synced_at: datetime,
    ) -> _SyncFileResult:
        item = await self._uow.repo_sync_repo.get_item_by_path(repo_sync_id=repo_sync.id, path=file.path)
        if item is not None and item.sha == file.sha:
            return _SyncFileResult(state="skipped", document=None)

        if item is None:
            document = self._create_document(repo_sync, file)
            await self._uow.document_repo.create(document)
            await self._uow.document_activity_repo.record_event(
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
            await self._uow.document_repo.update(document)
            state = "updated"

        await self._uow.repo_sync_repo.upsert_item(
            repo_sync_id=repo_sync.id,
            path=file.path,
            sha=file.sha,
            document_id=document.id,
            source_url=file.html_url,
            synced_at=synced_at,
        )
        return _SyncFileResult(state=state, document=document)

    async def _load_item_document(self, item: RepoSyncItemDTO) -> DocumentEntity:
        document = await self._uow.document_repo.get_by_id(item.document_id)
        if document is None:
            raise ResourceNotFoundException("synced document not found")
        return document

    def _create_document(self, repo_sync: RepoSyncDTO, file: MarkdownRepoFileDTO) -> DocumentEntity:
        return DocumentEntity.create(
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


@dataclass(frozen=True, slots=True)
class _SyncFileResult:
    state: str
    document: DocumentEntity | None
