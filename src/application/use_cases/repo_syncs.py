from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import PurePosixPath
from typing import TYPE_CHECKING
from uuid import UUID

from src.application.dtos.repo_sync_dtos import (
    CreateRepoSyncDTO,
    RepoSyncDTO,
    RepoSyncListDTO,
    RepoSyncRunResultDTO,
    RunRepoSyncDTO,
)
from src.application.use_cases.documents.queue_document_processing import queue_document_processing
from src.domain.entities.document_entity import DocumentEntity
from src.domain.exceptions import (
    DomainException,
    IntegrationRequestException,
    ResourceNotFoundException,
    ValidationException,
)
from src.domain.value_objects.document_type import DocumentType

if TYPE_CHECKING:
    from src.application.dtos.repo_sync_dtos import MarkdownRepoFileDTO, RepoSyncItemDTO
    from src.application.ports.cache.document_status_cache import IDocumentStatusCache
    from src.application.ports.ingestion.task_dispatcher import ITaskDispatcher
    from src.application.ports.integrations.github_repository_client import IGitHubRepositoryClient
    from src.application.ports.persistence.unit_of_work import IUnitOfWork


_REPO_URL_PATTERN = re.compile(r"^(?:https://github\.com/|git@github\.com:)(?P<owner>[^/\s]+)/(?P<repo>[^/\s]+?)(?:\.git)?/?$")
_MIN_SYNC_FILES = 1
_MAX_SYNC_FILES = 250


class ListRepoSyncsUseCase:
    def __init__(self, uow: IUnitOfWork) -> None:
        self._uow = uow

    async def __call__(self, *, user_id: UUID) -> RepoSyncListDTO:
        async with self._uow:
            items = await self._uow.repo_sync_repo.list_by_user_id(user_id)
        return RepoSyncListDTO(items=items)


class CreateRepoSyncUseCase:
    def __init__(self, uow: IUnitOfWork) -> None:
        self._uow = uow

    async def __call__(self, dto: CreateRepoSyncDTO) -> RepoSyncDTO:
        repo_ref = parse_github_repo_url(dto.repo_url)
        branch = dto.branch.strip() or "main"
        async with self._uow:
            collection = await self._uow.collection_repo.get_by_id(dto.collection_id)
            if collection is None or collection.user_id != dto.user_id:
                raise ResourceNotFoundException("collection not found")
            existing = await self._uow.repo_sync_repo.get_by_repo(
                user_id=dto.user_id,
                owner=repo_ref.owner,
                repo=repo_ref.repo,
                branch=branch,
            )
            if existing is not None:
                return existing
            repo_sync = await self._uow.repo_sync_repo.create(
                id=uuid.uuid4(),
                user_id=dto.user_id,
                collection_id=dto.collection_id,
                provider="github",
                owner=repo_ref.owner,
                repo=repo_ref.repo,
                branch=branch,
            )
            await self._uow.commit()
            return repo_sync


class RunRepoSyncUseCase:
    def __init__(
        self,
        uow: IUnitOfWork,
        github_client: IGitHubRepositoryClient,
        status_cache: IDocumentStatusCache,
        task_dispatcher: ITaskDispatcher,
    ) -> None:
        self._uow = uow
        self._github_client = github_client
        self._status_cache = status_cache
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
            repo_sync, created, updated, skipped, deleted, changed_documents = await self._sync_files(repo_sync, fetch_result.files)
            await self._queue_changed_documents(changed_documents)
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
    ) -> tuple[RepoSyncDTO, int, int, int, int, list[DocumentEntity]]:
        now = datetime.now(UTC)
        changed_documents: list[DocumentEntity] = []
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
                    if result.document is not None:
                        changed_documents.append(result.document)
                elif result.state == "updated":
                    updated += 1
                    if result.document is not None:
                        changed_documents.append(result.document)
                else:
                    skipped += 1

            for item in stale_repo_items(existing_items, current_paths):
                await self._uow.repo_sync_repo.delete_item(item.id)
                await self._uow.document_repo.delete(item.document_id)
                deleted += 1

            repo_sync = await self._uow.repo_sync_repo.update_state(
                repo_sync_id=repo_sync.id,
                status="completed",
                last_error=None,
                last_synced_at=now,
            )
            await self._uow.commit()

        return repo_sync, created, updated, skipped, deleted, changed_documents

    async def _queue_changed_documents(self, changed_documents: list[DocumentEntity]) -> None:
        for document in changed_documents:
            await queue_document_processing(
                document=document,
                uow=self._uow,
                status_cache=self._status_cache,
                task_dispatcher=self._task_dispatcher,
                message="Queued from GitHub sync.",
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
    ) -> None:
        async with self._uow:
            await self._uow.repo_sync_repo.update_state(
                repo_sync_id=repo_sync_id,
                status=status,
                last_error=last_error,
            )
            await self._uow.commit()

    async def _mark_repo_sync_failed(self, repo_sync_id: UUID, message: str) -> None:
        try:
            await self._set_repo_sync_state(repo_sync_id, status="failed", last_error=message)
        except Exception:
            return

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
            document.rename(_document_title_from_path(file.path))
            document.update_content(
                raw_content=file.content,
                word_count=len(file.content.split()),
                language=None,
            )
            document.mark_queued()
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
        document = DocumentEntity.create(
            id=uuid.uuid4(),
            user_id=repo_sync.user_id,
            collection_id=repo_sync.collection_id,
            title=_document_title_from_path(file.path),
            type=DocumentType.MARKDOWN,
            source_url=file.html_url,
            raw_content=file.content,
            file_size_bytes=len(file.content.encode()),
            word_count=len(file.content.split()),
        )
        document.mark_queued()
        return document


@dataclass(frozen=True, slots=True)
class GitHubRepoRef:
    owner: str
    repo: str


@dataclass(frozen=True, slots=True)
class _SyncFileResult:
    state: str
    document: DocumentEntity | None


def parse_github_repo_url(repo_url: str) -> GitHubRepoRef:
    match = _REPO_URL_PATTERN.match(repo_url.strip())
    if match is None:
        raise ValidationException("repo_url must be a GitHub repository URL")
    return GitHubRepoRef(owner=match.group("owner"), repo=match.group("repo"))


def _document_title_from_path(path: str) -> str:
    stem = PurePosixPath(path).stem.strip()
    return stem.replace("-", " ").replace("_", " ") or path


def stale_repo_items(items: list[RepoSyncItemDTO], current_paths: set[str]) -> list[RepoSyncItemDTO]:
    return [item for item in items if item.path not in current_paths]


def normalize_max_files(max_files: int) -> int:
    if max_files < _MIN_SYNC_FILES:
        raise ValidationException("max_files must be at least 1")
    return min(max_files, _MAX_SYNC_FILES)


def unique_repo_files(files: list[MarkdownRepoFileDTO]) -> list[MarkdownRepoFileDTO]:
    unique: dict[str, MarkdownRepoFileDTO] = {}
    for file in files:
        unique[file.path] = file
    return list(unique.values())


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


def sanitized_repo_sync_exception(exc: Exception, message: str) -> DomainException:
    if isinstance(exc, ValidationException):
        return ValidationException(message)
    return IntegrationRequestException(message)
