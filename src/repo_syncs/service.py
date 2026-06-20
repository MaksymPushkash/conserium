from __future__ import annotations

import fnmatch
import logging
import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import PurePosixPath
from typing import TYPE_CHECKING, Protocol
from uuid import UUID

from fastapi import Depends

from src.collections.repository import CollectionRepository
from src.documents.activity_repository import DocumentActivityRepository
from src.documents.document_repository import DocumentRepository
from src.documents.status import DocumentStatus
from src.documents.types import DocumentType
from src.kit.exceptions import (
    DomainException,
    IntegrationRequestException,
    ResourceNotFoundException,
    ValidationException,
)
from src.models.document import DocumentModel
from src.postgres import AsyncSession, get_db_session, get_session_factory
from src.repo_syncs.github_repository_client import GitHubRepositoryClient
from src.repo_syncs.repository import RepoSyncRepository
from src.repo_syncs.schemas import (
    CreateRepoSyncDTO,
    CreateRepoSyncRequest,
    MarkdownRepoFileDTO,
    RepoSyncDTO,
    RepoSyncItemDTO,
    RepoSyncListDTO,
    RepoSyncListResponse,
    RepoSyncOutboxDTO,
    RepoSyncResponse,
    RepoSyncRunResponse,
    RepoSyncRunResultDTO,
    RunRepoSyncDTO,
    RunRepoSyncRequest,
)
from src.worker.dispatcher import CeleryTaskDispatcher

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from src.documents.status_cache import IDocumentStatusCache
    from src.integrations.clients import GitHubRepositoryClientProtocol
    from src.worker.dispatcher import ITaskDispatcher


logger = logging.getLogger(__name__)

_REPO_URL_PATTERN = re.compile(r"^(?:https://github\.com/|git@github\.com:)(?P<owner>[^/\s]+)/(?P<repo>[^/\s]+?)(?:\.git)?/?$")
_MIN_SYNC_FILES = 1
_MAX_SYNC_FILES = 250
_DEFAULT_INCLUDE_PATHS = ("README.md", "docs/**/*.md", "**/*.md")
_DEFAULT_EXCLUDE_PATHS = ("node_modules/**", ".git/**", "dist/**")
_MAX_OUTBOX_ATTEMPTS = 5
_OUTBOX_LOCK_TIMEOUT = timedelta(minutes=15)
_OUTBOX_BATCH_LIMIT = 100


class _RepoPathItem(Protocol):
    @property
    def path(self) -> str: ...


@dataclass(frozen=True, slots=True)
class GitHubRepoRef:
    owner: str
    repo: str


@dataclass(frozen=True, slots=True)
class RepoSyncOutboxDrainResult:
    claimed: int
    dispatched: int
    failed: int
    permanently_failed: int


@dataclass(frozen=True, slots=True)
class _SyncFileResult:
    state: str
    document: DocumentModel | None


class RepoSyncService:
    def __init__(
        self,
        session: AsyncSession,
        collection_repo: CollectionRepository,
        document_repo: DocumentRepository,
        document_activity_repo: DocumentActivityRepository,
        repo_sync_repo: RepoSyncRepository,
    ) -> None:
        self.session = session
        self.collection_repo = collection_repo
        self.document_repo = document_repo
        self.document_activity_repo = document_activity_repo
        self.repo_sync_repo = repo_sync_repo

    async def list(self, *, user_id: UUID) -> RepoSyncListResponse:
        items = await self.repo_sync_repo.list_by_user_id(user_id)
        return to_repo_sync_list_response(RepoSyncListDTO(items=items))

    async def create(self, *, user_id: UUID, body: CreateRepoSyncRequest) -> RepoSyncResponse:
        dto = to_create_repo_sync_dto(body, user_id)
        repo_ref = parse_github_repo_url(dto.repo_url)
        branch = dto.branch.strip() or "main"
        include_paths = normalize_repo_path_patterns(dto.include_paths, _DEFAULT_INCLUDE_PATHS)
        exclude_paths = normalize_repo_path_patterns(dto.exclude_paths, _DEFAULT_EXCLUDE_PATHS)
        collection = await self.collection_repo.get_by_id(dto.collection_id)
        if collection is None or collection.user_id != dto.user_id:
            raise ResourceNotFoundException("collection not found")
        existing = await self.repo_sync_repo.get_by_repo(
            user_id=dto.user_id,
            owner=repo_ref.owner,
            repo=repo_ref.repo,
            branch=branch,
        )
        if existing is not None:
            existing = await self.repo_sync_repo.update_filters(
                repo_sync_id=existing.id,
                include_paths=include_paths,
                exclude_paths=exclude_paths,
            )
            await self.session.flush()
            return to_repo_sync_response(existing)
        repo_sync = await self.repo_sync_repo.create(
            id=uuid.uuid4(),
            user_id=dto.user_id,
            collection_id=dto.collection_id,
            provider="github",
            owner=repo_ref.owner,
            repo=repo_ref.repo,
            branch=branch,
            include_paths=include_paths,
            exclude_paths=exclude_paths,
        )
        await self.session.flush()
        return to_repo_sync_response(repo_sync)

class RepoSyncRunner:
    def __init__(
        self,
        session: AsyncSession,
        document_repo: DocumentRepository,
        document_activity_repo: DocumentActivityRepository,
        repo_sync_repo: RepoSyncRepository,
        github_client: GitHubRepositoryClientProtocol,
        task_dispatcher: ITaskDispatcher,
    ) -> None:
        self._session = session
        self._document_repo = document_repo
        self._document_activity_repo = document_activity_repo
        self._repo_sync_repo = repo_sync_repo
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

    async def _load_user_repo_sync(self, user_id: UUID, repo_sync_id: UUID) -> RepoSyncDTO:
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
    ) -> RepoSyncDTO:
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
        repo_sync: RepoSyncDTO,
        file: MarkdownRepoFileDTO,
        synced_at: datetime,
    ) -> _SyncFileResult:
        item = await self._repo_sync_repo.get_item_by_path(repo_sync_id=repo_sync.id, path=file.path)
        if item is not None and item.sha == file.sha:
            return _SyncFileResult(state="skipped", document=None)

        if item is None:
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

    async def _load_item_document(self, item: RepoSyncItemDTO) -> DocumentModel:
        document = await self._document_repo.get_by_id(item.document_id)
        if document is None:
            raise ResourceNotFoundException("synced document not found")
        return document

    def _create_document(self, repo_sync: RepoSyncDTO, file: MarkdownRepoFileDTO) -> DocumentModel:
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


class RepoSyncExecutor:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def run(self, *, user_id: UUID, repo_sync_id: UUID, body: RunRepoSyncRequest) -> RepoSyncRunResponse:
        async with self._session_factory() as session:
            result = await RepoSyncRunner(
                session=session,
                document_repo=DocumentRepository.from_session(session),
                document_activity_repo=DocumentActivityRepository.from_session(session),
                repo_sync_repo=RepoSyncRepository.from_session(session),
                github_client=GitHubRepositoryClient(),
                task_dispatcher=CeleryTaskDispatcher(),
            )(to_run_repo_sync_dto(body, user_id, repo_sync_id))
            return to_repo_sync_run_response(result)


class RepoSyncOutboxDrainer:
    def __init__(
        self,
        session: AsyncSession,
        document_repo: DocumentRepository,
        repo_sync_repo: RepoSyncRepository,
        status_cache: IDocumentStatusCache,
        task_dispatcher: ITaskDispatcher,
    ) -> None:
        self._session = session
        self._document_repo = document_repo
        self._repo_sync_repo = repo_sync_repo
        self._status_cache = status_cache
        self._task_dispatcher = task_dispatcher

    async def __call__(self, *, limit: int = _OUTBOX_BATCH_LIMIT) -> RepoSyncOutboxDrainResult:
        outbox_items = await self._claim_outbox(limit)
        dispatched = 0
        failed = 0
        permanently_failed = 0

        for outbox in outbox_items:
            try:
                await self._dispatch_outbox_item(outbox)
                dispatched += 1
            except Exception as exc:
                retryable = outbox.attempts < _MAX_OUTBOX_ATTEMPTS
                await self._mark_outbox_failed(outbox, exc, retryable=retryable)
                failed += 1
                if not retryable:
                    permanently_failed += 1
                    await self._mark_repo_sync_failed(outbox.repo_sync_id, "GitHub sync dispatch failed after retries.")

        return RepoSyncOutboxDrainResult(
            claimed=len(outbox_items),
            dispatched=dispatched,
            failed=failed,
            permanently_failed=permanently_failed,
        )

    async def _claim_outbox(self, limit: int) -> list[RepoSyncOutboxDTO]:
        now = datetime.now(UTC)
        outbox_items = await self._repo_sync_repo.claim_outbox_batch(
            limit=limit,
            locked_at=now,
            stale_before=now - _OUTBOX_LOCK_TIMEOUT,
            max_attempts=_MAX_OUTBOX_ATTEMPTS,
        )
        await self._session.commit()
        return outbox_items

    async def _dispatch_outbox_item(self, outbox: RepoSyncOutboxDTO) -> None:
        document = await self._load_document(outbox.document_id)
        if document is None:
            await self._mark_outbox_dispatched(outbox)
            return

        if document.status in (DocumentStatus.QUEUED, DocumentStatus.PROCESSING, DocumentStatus.READY):
            await self._mark_outbox_dispatched(outbox)
            return

        await self._status_cache.set_status(
            outbox.document_id,
            status=DocumentStatus.QUEUED.value,
            progress=0,
            message="Queued from GitHub sync.",
        )
        await self._task_dispatcher.dispatch_process_document(
            str(outbox.document_id),
            task_id=repo_sync_outbox_task_id(outbox.id),
        )

        document = await self._document_repo.get_by_id(outbox.document_id)
        if document is not None:
            document.mark_queued()
            await self._document_repo.update(document)
        await self._repo_sync_repo.mark_outbox_dispatched(outbox.id, datetime.now(UTC))
        active_outbox = await self._repo_sync_repo.has_active_outbox(outbox.repo_sync_id)
        if not active_outbox:
            await self._repo_sync_repo.update_state(
                repo_sync_id=outbox.repo_sync_id,
                status="completed",
                last_error=None,
                last_synced_at=datetime.now(UTC),
            )
        await self._session.commit()

    async def _load_document(self, document_id: UUID) -> DocumentModel | None:
        return await self._document_repo.get_by_id(document_id)

    async def _mark_outbox_dispatched(self, outbox: RepoSyncOutboxDTO) -> None:
        await self._repo_sync_repo.mark_outbox_dispatched(outbox.id, datetime.now(UTC))
        active_outbox = await self._repo_sync_repo.has_active_outbox(outbox.repo_sync_id)
        if not active_outbox:
            await self._repo_sync_repo.update_state(
                repo_sync_id=outbox.repo_sync_id,
                status="completed",
                last_error=None,
                last_synced_at=datetime.now(UTC),
            )
        await self._session.commit()

    async def _mark_outbox_failed(self, outbox: RepoSyncOutboxDTO, exc: Exception, *, retryable: bool) -> None:
        await self._repo_sync_repo.mark_outbox_failed(
            outbox.id,
            last_error=sanitize_outbox_error(exc),
            retryable=retryable,
        )
        await self._session.commit()

    async def _mark_repo_sync_failed(self, repo_sync_id: UUID, message: str) -> None:
        try:
            await self._repo_sync_repo.update_state(repo_sync_id=repo_sync_id, status="failed", last_error=message)
            await self._session.commit()
        except Exception as exc:
            logger.exception(
                "repo_sync_failed_state_persistence_failed",
                extra={
                    "repo_sync_id": str(repo_sync_id),
                    "error_type": type(exc).__name__,
                    "sanitized_error": message,
                },
            )


def build_repo_sync_service(session: AsyncSession) -> RepoSyncService:
    return RepoSyncService(
        session=session,
        collection_repo=CollectionRepository.from_session(session),
        document_repo=DocumentRepository.from_session(session),
        document_activity_repo=DocumentActivityRepository.from_session(session),
        repo_sync_repo=RepoSyncRepository.from_session(session),
    )


def get_repo_sync_service(session: AsyncSession = Depends(get_db_session)) -> RepoSyncService:
    return build_repo_sync_service(session)


def get_repo_sync_executor() -> RepoSyncExecutor:
    return RepoSyncExecutor(get_session_factory())


def to_create_repo_sync_dto(body: CreateRepoSyncRequest, user_id: UUID) -> CreateRepoSyncDTO:
    return CreateRepoSyncDTO(
        user_id=user_id,
        collection_id=body.collection_id,
        repo_url=body.repo_url,
        branch=body.branch,
        include_paths=body.include_paths,
        exclude_paths=body.exclude_paths,
    )


def to_run_repo_sync_dto(body: RunRepoSyncRequest, user_id: UUID, repo_sync_id: UUID) -> RunRepoSyncDTO:
    return RunRepoSyncDTO(user_id=user_id, repo_sync_id=repo_sync_id, max_files=body.max_files)


def to_repo_sync_response(dto: RepoSyncDTO) -> RepoSyncResponse:
    return RepoSyncResponse(
        id=dto.id,
        collection_id=dto.collection_id,
        provider=dto.provider,
        owner=dto.owner,
        repo=dto.repo,
        branch=dto.branch,
        include_paths=dto.include_paths,
        exclude_paths=dto.exclude_paths,
        status=dto.status,
        last_error=dto.last_error,
        last_synced_at=dto.last_synced_at,
        created_at=dto.created_at,
        updated_at=dto.updated_at,
    )


def to_repo_sync_list_response(dto: RepoSyncListDTO) -> RepoSyncListResponse:
    return RepoSyncListResponse(items=[to_repo_sync_response(item) for item in dto.items])


def to_repo_sync_run_response(dto: RepoSyncRunResultDTO) -> RepoSyncRunResponse:
    return RepoSyncRunResponse(
        repo_sync=to_repo_sync_response(dto.repo_sync),
        created=dto.created,
        updated=dto.updated,
        skipped=dto.skipped,
        deleted=dto.deleted,
        warnings=dto.warnings,
    )


def parse_github_repo_url(repo_url: str) -> GitHubRepoRef:
    match = _REPO_URL_PATTERN.match(repo_url.strip())
    if match is None:
        raise ValidationException("repo_url must be a GitHub repository URL")
    return GitHubRepoRef(owner=match.group("owner"), repo=match.group("repo"))


def document_title_from_path(path: str) -> str:
    stem = PurePosixPath(path).stem.strip()
    return stem.replace("-", " ").replace("_", " ") or path


def stale_repo_items[T: _RepoPathItem](items: list[T], current_paths: set[str]) -> list[T]:
    return [item for item in items if item.path not in current_paths]


def normalize_max_files(max_files: int) -> int:
    if max_files < _MIN_SYNC_FILES:
        raise ValidationException("max_files must be at least 1")
    return min(max_files, _MAX_SYNC_FILES)


def unique_repo_files[T: _RepoPathItem](files: list[T]) -> list[T]:
    unique: dict[str, T] = {}
    for file in files:
        unique[file.path] = file
    return list(unique.values())


def normalize_repo_path_patterns(patterns: list[str] | None, default: tuple[str, ...]) -> list[str]:
    if patterns is None:
        return list(default)
    cleaned = [pattern.strip() for pattern in patterns if pattern.strip()]
    return cleaned or list(default)


def filter_repo_files[T: _RepoPathItem](
    files: list[T],
    *,
    include_paths: list[str],
    exclude_paths: list[str],
) -> list[T]:
    return [
        file
        for file in files
        if _path_matches_any(file.path, include_paths)
        and not _path_matches_any(file.path, exclude_paths)
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
    "GitHubRepoRef",
    "RepoSyncExecutor",
    "RepoSyncOutboxDrainResult",
    "RepoSyncOutboxDrainer",
    "RepoSyncRunner",
    "RepoSyncService",
    "document_title_from_path",
    "filter_repo_files",
    "get_repo_sync_executor",
    "get_repo_sync_service",
    "normalize_max_files",
    "normalize_repo_path_patterns",
    "parse_github_repo_url",
    "repo_sync_outbox_task_id",
    "sanitize_outbox_error",
    "sanitize_repo_sync_error",
    "sanitized_repo_sync_exception",
    "stale_repo_items",
    "to_create_repo_sync_dto",
    "to_repo_sync_list_response",
    "to_repo_sync_response",
    "to_repo_sync_run_response",
    "to_run_repo_sync_dto",
    "unique_repo_files",
]
