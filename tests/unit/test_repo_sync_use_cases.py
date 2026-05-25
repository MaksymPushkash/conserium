import logging
from datetime import UTC, datetime
from uuid import UUID, uuid4

import httpx
import pytest

from src.application.dtos.repo_sync_dtos import (
    MarkdownRepoFetchResultDTO,
    MarkdownRepoFileDTO,
    RepoSyncDTO,
    RepoSyncItemDTO,
    RunRepoSyncDTO,
)
from src.application.use_cases.repo_syncs import (
    DrainRepoSyncOutboxUseCase,
    RunRepoSyncUseCase,
    filter_repo_files,
    normalize_max_files,
    normalize_repo_path_patterns,
    parse_github_repo_url,
    sanitize_repo_sync_error,
    sanitized_repo_sync_exception,
    stale_repo_items,
    unique_repo_files,
)
from src.domain.exceptions import IntegrationRequestException, ValidationException
from src.domain.value_objects.document_status import DocumentStatus
from src.infrastructure.integrations.github_repository_client import GitHubRepositoryClient


def test_parse_github_repo_url_accepts_https_url() -> None:
    repo = parse_github_repo_url("https://github.com/example/docs")

    assert repo.owner == "example"
    assert repo.repo == "docs"


def test_parse_github_repo_url_accepts_ssh_url() -> None:
    repo = parse_github_repo_url("git@github.com:example/docs.git")

    assert repo.owner == "example"
    assert repo.repo == "docs"


def test_parse_github_repo_url_rejects_non_github_url() -> None:
    with pytest.raises(ValidationException):
        parse_github_repo_url("https://gitlab.com/example/docs")


def test_stale_repo_items_returns_synced_items_missing_from_latest_tree() -> None:
    current = _repo_item("docs/current.md")
    stale = _repo_item("docs/removed.md")

    result = stale_repo_items([current, stale], {"docs/current.md"})

    assert result == [stale]


def test_normalize_max_files_rejects_zero() -> None:
    with pytest.raises(ValidationException):
        normalize_max_files(0)


def test_normalize_max_files_caps_large_values() -> None:
    assert normalize_max_files(999) == 250


def test_unique_repo_files_keeps_latest_duplicate_path() -> None:
    first = _repo_file("docs/readme.md", "first")
    second = _repo_file("docs/readme.md", "second")

    assert unique_repo_files([first, second]) == [second]


def test_filter_repo_files_applies_include_and_exclude_patterns() -> None:
    files = [
        _repo_file("README.md", "readme"),
        _repo_file("docs/guide.md", "guide"),
        _repo_file("node_modules/pkg/readme.md", "vendor"),
        _repo_file("src/app.py", "source"),
    ]

    result = filter_repo_files(
        files,
        include_paths=["README.md", "**/*.md"],
        exclude_paths=["node_modules/**"],
    )

    assert [file.path for file in result] == ["README.md", "docs/guide.md"]


def test_filtered_repo_paths_drive_stale_deletion_scope() -> None:
    filtered_files = filter_repo_files(
        [_repo_file("docs/current.md", "current"), _repo_file("drafts/ignored.md", "ignored")],
        include_paths=["docs/*.md"],
        exclude_paths=[],
    )
    current_paths = {file.path for file in filtered_files}
    stale = stale_repo_items(
        [_repo_item("docs/current.md"), _repo_item("drafts/ignored.md")],
        current_paths,
    )

    assert [item.path for item in stale] == ["drafts/ignored.md"]


def test_normalize_repo_path_patterns_uses_default_when_empty() -> None:
    assert normalize_repo_path_patterns([" ", ""], ("**/*.md",)) == ["**/*.md"]


def test_sanitize_repo_sync_error_hides_raw_exception_details() -> None:
    result = sanitize_repo_sync_error(RuntimeError("403 token ghp_secret leaked"))

    assert result == "GitHub rate limit or access policy blocked this sync."
    assert "secret" not in result


def test_sanitized_repo_sync_exception_preserves_validation_error_type() -> None:
    result = sanitized_repo_sync_exception(ValidationException("bad repo"), "bad repo")

    assert isinstance(result, ValidationException)


@pytest.mark.asyncio
async def test_github_client_rejects_truncated_tree(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("src.infrastructure.integrations.github_repository_client.httpx.AsyncClient", _TruncatedTreeClient)
    client = GitHubRepositoryClient(token=None)

    with pytest.raises(IntegrationRequestException, match="tree is too large"):
        await client.fetch_markdown_files(owner="owner", repo="repo", branch="main", max_files=10)


@pytest.mark.asyncio
async def test_github_client_returns_partial_files_with_warning(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("src.infrastructure.integrations.github_repository_client.httpx.AsyncClient", _PartialRawClient)
    client = GitHubRepositoryClient(token=None)

    result = await client.fetch_markdown_files(owner="owner", repo="repo", branch="main", max_files=10)

    assert [file.path for file in result.files] == ["docs/ok.md"]
    assert result.warnings == ["Skipped 1 Markdown file that could not be fetched."]


@pytest.mark.asyncio
async def test_run_repo_sync_marks_failed_when_database_sync_fails() -> None:
    repo_sync = _repo_sync()
    uow = _FailingSyncUow(repo_sync)
    use_case = RunRepoSyncUseCase(
        uow=uow,  # type: ignore[arg-type]
        github_client=_SuccessfulGitHubClient(),  # type: ignore[arg-type]
        task_dispatcher=_NoopTaskDispatcher(),  # type: ignore[arg-type]
    )

    with pytest.raises(IntegrationRequestException):
        await use_case(RunRepoSyncDTO(user_id=repo_sync.user_id, repo_sync_id=repo_sync.id))

    assert uow.repo_sync_repo.states == ["running", "failed"]


@pytest.mark.asyncio
async def test_run_repo_sync_logs_when_failed_state_persistence_fails(caplog: pytest.LogCaptureFixture) -> None:
    repo_sync = _repo_sync()
    uow = _FailedStatePersistenceUow(repo_sync)
    use_case = RunRepoSyncUseCase(
        uow=uow,  # type: ignore[arg-type]
        github_client=_SuccessfulGitHubClient(),  # type: ignore[arg-type]
        task_dispatcher=_NoopTaskDispatcher(),  # type: ignore[arg-type]
    )

    with (
        caplog.at_level(logging.ERROR, logger="src.application.use_cases.repo_syncs"),
        pytest.raises(IntegrationRequestException),
    ):
        await use_case(RunRepoSyncDTO(user_id=repo_sync.user_id, repo_sync_id=repo_sync.id))

    assert "repo_sync_failed_state_persistence_failed" in caplog.text


@pytest.mark.asyncio
async def test_run_repo_sync_keeps_queueing_when_outbox_drain_enqueue_fails() -> None:
    repo_sync = _repo_sync()
    uow = _QueueFailureUow(repo_sync)
    use_case = RunRepoSyncUseCase(
        uow=uow,  # type: ignore[arg-type]
        github_client=_SuccessfulGitHubClient(),  # type: ignore[arg-type]
        task_dispatcher=_FailingTaskDispatcher(),  # type: ignore[arg-type]
    )

    result = await use_case(RunRepoSyncDTO(user_id=repo_sync.user_id, repo_sync_id=repo_sync.id))

    assert result.repo_sync.status == "queueing"
    assert uow.repo_sync_repo.states == ["running", "queueing"]


@pytest.mark.asyncio
async def test_outbox_drainer_dispatches_before_marking_document_queued() -> None:
    repo_sync = _repo_sync()
    outbox = _Outbox(repo_sync_id=repo_sync.id, document_id=uuid4(), task_name="process_document")
    document = _DispatchDocument(outbox.document_id)
    uow = _DrainUow(repo_sync, outbox, document)
    dispatcher = _RecordingTaskDispatcher()
    use_case = DrainRepoSyncOutboxUseCase(
        uow=uow,  # type: ignore[arg-type]
        status_cache=_RecordingStatusCache(),  # type: ignore[arg-type]
        task_dispatcher=dispatcher,  # type: ignore[arg-type]
    )

    result = await use_case(limit=10)

    assert result.dispatched == 1
    assert dispatcher.document_ids == [str(outbox.document_id)]
    assert dispatcher.task_ids == [f"repo-sync-outbox-{outbox.id}"]
    assert document.queued is True
    assert outbox.status == "dispatched"
    assert uow.repo_sync_repo.states == ["completed"]


@pytest.mark.asyncio
async def test_outbox_drainer_does_not_mark_queued_when_dispatch_prerequisite_fails() -> None:
    repo_sync = _repo_sync()
    outbox = _Outbox(repo_sync_id=repo_sync.id, document_id=uuid4(), task_name="process_document")
    document = _DispatchDocument(outbox.document_id)
    uow = _DrainUow(repo_sync, outbox, document)
    dispatcher = _RecordingTaskDispatcher()
    use_case = DrainRepoSyncOutboxUseCase(
        uow=uow,  # type: ignore[arg-type]
        status_cache=_FailingStatusCache(),  # type: ignore[arg-type]
        task_dispatcher=dispatcher,  # type: ignore[arg-type]
    )

    result = await use_case(limit=10)

    assert result.failed == 1
    assert dispatcher.document_ids == []
    assert document.queued is False
    assert outbox.status == "pending"
    assert outbox.attempts == 1
    assert outbox.last_error == "cache down"


@pytest.mark.asyncio
async def test_outbox_drainer_marks_already_started_document_without_duplicate_dispatch() -> None:
    repo_sync = _repo_sync()
    outbox = _Outbox(repo_sync_id=repo_sync.id, document_id=uuid4(), task_name="process_document")
    document = _DispatchDocument(outbox.document_id, status=DocumentStatus.PROCESSING)
    uow = _DrainUow(repo_sync, outbox, document)
    dispatcher = _RecordingTaskDispatcher()
    use_case = DrainRepoSyncOutboxUseCase(
        uow=uow,  # type: ignore[arg-type]
        status_cache=_RecordingStatusCache(),  # type: ignore[arg-type]
        task_dispatcher=dispatcher,  # type: ignore[arg-type]
    )

    result = await use_case(limit=10)

    assert result.dispatched == 1
    assert dispatcher.document_ids == []
    assert outbox.status == "dispatched"
    assert uow.repo_sync_repo.states == ["completed"]


@pytest.mark.asyncio
async def test_outbox_drainer_marks_repo_sync_failed_after_retry_budget() -> None:
    repo_sync = _repo_sync()
    outbox = _Outbox(repo_sync_id=repo_sync.id, document_id=uuid4(), task_name="process_document")
    outbox.attempts = 4
    document = _DispatchDocument(outbox.document_id)
    uow = _DrainUow(repo_sync, outbox, document)
    use_case = DrainRepoSyncOutboxUseCase(
        uow=uow,  # type: ignore[arg-type]
        status_cache=_FailingStatusCache(),  # type: ignore[arg-type]
        task_dispatcher=_RecordingTaskDispatcher(),  # type: ignore[arg-type]
    )

    result = await use_case(limit=10)

    assert result.permanently_failed == 1
    assert outbox.status == "failed"
    assert uow.repo_sync_repo.states == ["failed"]


def _repo_item(path: str) -> RepoSyncItemDTO:
    now = datetime(2026, 5, 17, tzinfo=UTC)
    return RepoSyncItemDTO(
        id=uuid4(),
        repo_sync_id=uuid4(),
        path=path,
        sha="sha",
        document_id=uuid4(),
        source_url=f"https://github.com/example/docs/blob/main/{path}",
        last_synced_at=now,
        created_at=now,
        updated_at=None,
    )


def _repo_file(path: str, sha: str) -> MarkdownRepoFileDTO:
    return MarkdownRepoFileDTO(path=path, sha=sha, content="content", html_url=f"https://github.com/example/docs/blob/main/{path}")


def _repo_sync() -> RepoSyncDTO:
    now = datetime(2026, 5, 17, tzinfo=UTC)
    return RepoSyncDTO(
        id=uuid4(),
        user_id=uuid4(),
        collection_id=uuid4(),
        provider="github",
        owner="example",
        repo="docs",
        branch="main",
        include_paths=["README.md", "**/*.md"],
        exclude_paths=["node_modules/**"],
        status="pending",
        last_error=None,
        last_synced_at=None,
        created_at=now,
        updated_at=None,
    )


class _TruncatedTreeClient:
    def __init__(self, *args: object, **kwargs: object) -> None:
        pass

    async def __aenter__(self) -> "_TruncatedTreeClient":
        return self

    async def __aexit__(self, *args: object) -> None:
        pass

    async def get(self, url: str, **kwargs: object) -> httpx.Response:
        return httpx.Response(200, json={"truncated": True, "tree": []}, request=httpx.Request("GET", url))


class _PartialRawClient:
    def __init__(self, *args: object, **kwargs: object) -> None:
        pass

    async def __aenter__(self) -> "_PartialRawClient":
        return self

    async def __aexit__(self, *args: object) -> None:
        pass

    async def get(self, url: str, **kwargs: object) -> httpx.Response:
        if "/git/trees/" in url:
            payload = {
                "tree": [
                    {"type": "blob", "path": "docs/ok.md", "sha": "ok", "size": 100},
                    {"type": "blob", "path": "docs/fail.md", "sha": "fail", "size": 100},
                ]
            }
            return httpx.Response(200, json=payload, request=httpx.Request("GET", url))
        if url.endswith("/docs/ok.md"):
            return httpx.Response(200, text="# Ok", request=httpx.Request("GET", url))
        return httpx.Response(500, text="error", request=httpx.Request("GET", url))


class _SuccessfulGitHubClient:
    async def fetch_markdown_files(self, **kwargs: object) -> MarkdownRepoFetchResultDTO:
        return MarkdownRepoFetchResultDTO(files=[_repo_file("docs/readme.md", "sha")], warnings=[])


class _FailingSyncUow:
    def __init__(self, repo_sync: RepoSyncDTO) -> None:
        self.repo_sync_repo = _FailingRepoSyncRepo(repo_sync)

    async def __aenter__(self) -> "_FailingSyncUow":
        return self

    async def __aexit__(self, *args: object) -> None:
        pass

    async def commit(self) -> None:
        pass


class _FailingRepoSyncRepo:
    def __init__(self, repo_sync: RepoSyncDTO) -> None:
        self._repo_sync = repo_sync
        self.states: list[str] = []

    async def get_by_id(self, repo_sync_id):
        return self._repo_sync if repo_sync_id == self._repo_sync.id else None

    async def update_state(self, *, repo_sync_id, status, last_error=None, last_synced_at=None):
        self.states.append(status)
        return self._repo_sync

    async def list_items(self, repo_sync_id):
        raise RuntimeError("database write failed")


class _FailedStatePersistenceUow:
    def __init__(self, repo_sync: RepoSyncDTO) -> None:
        self.repo_sync_repo = _FailedStatePersistenceRepo(repo_sync)

    async def __aenter__(self) -> "_FailedStatePersistenceUow":
        return self

    async def __aexit__(self, *args: object) -> None:
        pass

    async def commit(self) -> None:
        pass


class _FailedStatePersistenceRepo:
    def __init__(self, repo_sync: RepoSyncDTO) -> None:
        self._repo_sync = repo_sync

    async def get_by_id(self, repo_sync_id):
        return self._repo_sync if repo_sync_id == self._repo_sync.id else None

    async def update_state(self, *, repo_sync_id, status, last_error=None, last_synced_at=None):
        if status == "failed":
            raise RuntimeError("database unavailable")
        return self._repo_sync

    async def list_items(self, repo_sync_id):
        raise RuntimeError("database write failed")


class _NoopTaskDispatcher:
    async def dispatch_repo_sync_outbox(self) -> None:
        return None


class _QueueFailureUow:
    def __init__(self, repo_sync: RepoSyncDTO) -> None:
        self.repo_sync_repo = _QueueFailureRepoSyncRepo(repo_sync)
        self.document_repo = _QueueFailureDocumentRepo()
        self.document_activity_repo = _QueueFailureActivityRepo()

    async def __aenter__(self) -> "_QueueFailureUow":
        return self

    async def __aexit__(self, *args: object) -> None:
        pass

    async def commit(self) -> None:
        pass


class _QueueFailureRepoSyncRepo:
    def __init__(self, repo_sync: RepoSyncDTO) -> None:
        self._repo_sync = repo_sync
        self.states: list[str] = []
        self.outbox: list[_Outbox] = []

    async def get_by_id(self, repo_sync_id):
        return self._repo_sync if repo_sync_id == self._repo_sync.id else None

    async def update_state(self, *, repo_sync_id, status, last_error=None, last_synced_at=None):
        self.states.append(status)
        return RepoSyncDTO(
            id=self._repo_sync.id,
            user_id=self._repo_sync.user_id,
            collection_id=self._repo_sync.collection_id,
            provider=self._repo_sync.provider,
            owner=self._repo_sync.owner,
            repo=self._repo_sync.repo,
            branch=self._repo_sync.branch,
            include_paths=self._repo_sync.include_paths,
            exclude_paths=self._repo_sync.exclude_paths,
            status=status,
            last_error=last_error,
            last_synced_at=last_synced_at or self._repo_sync.last_synced_at,
            created_at=self._repo_sync.created_at,
            updated_at=self._repo_sync.updated_at,
        )

    async def list_items(self, repo_sync_id):
        return []

    async def get_item_by_path(self, *, repo_sync_id, path):
        return None

    async def upsert_item(self, **kwargs):
        return None

    async def create_outbox(self, *, repo_sync_id, document_id, task_name):
        outbox = _Outbox(repo_sync_id=repo_sync_id, document_id=document_id, task_name=task_name)
        self.outbox.append(outbox)
        return outbox


class _QueueFailureDocumentRepo:
    def __init__(self) -> None:
        self.documents: dict[object, object] = {}

    async def create(self, document):
        self.documents[document.id] = document

    async def get_by_id(self, document_id):
        return self.documents.get(document_id)

    async def update(self, document):
        return None

    async def delete(self, document_id):
        return None


class _QueueFailureActivityRepo:
    async def record_event(self, **kwargs):
        return None


class _RecordingStatusCache:
    async def set_status(self, *args, **kwargs):
        return None


class _FailingStatusCache:
    async def set_status(self, *args, **kwargs):
        raise RuntimeError("cache down")


class _FailingTaskDispatcher:
    async def dispatch_repo_sync_outbox(self) -> None:
        raise RuntimeError("broker down")


class _RecordingTaskDispatcher:
    def __init__(self) -> None:
        self.document_ids: list[str] = []
        self.task_ids: list[str | None] = []

    async def dispatch_process_document(self, document_id: str, *, task_id: str | None = None) -> None:
        self.document_ids.append(document_id)
        self.task_ids.append(task_id)

    async def dispatch_repo_sync_outbox(self) -> None:
        return None


class _DrainUow:
    def __init__(self, repo_sync: RepoSyncDTO, outbox: "_Outbox", document: "_DispatchDocument") -> None:
        self.repo_sync_repo = _DrainRepoSyncRepo(repo_sync, outbox)
        self.document_repo = _DrainDocumentRepo(document)

    async def __aenter__(self) -> "_DrainUow":
        return self

    async def __aexit__(self, *args: object) -> None:
        pass

    async def commit(self) -> None:
        pass


class _DrainRepoSyncRepo:
    def __init__(self, repo_sync: RepoSyncDTO, outbox: "_Outbox") -> None:
        self._repo_sync = repo_sync
        self._outbox = outbox
        self.states: list[str] = []

    async def claim_outbox_batch(self, *, limit, locked_at, stale_before, max_attempts):
        if limit < 1 or self._outbox.status != "pending" or self._outbox.attempts >= max_attempts:
            return []
        self._outbox.status = "processing"
        self._outbox.locked_at = locked_at
        self._outbox.attempts += 1
        return [self._outbox]

    async def mark_outbox_dispatched(self, outbox_id, dispatched_at):
        self._outbox.status = "dispatched"
        self._outbox.locked_at = None
        self._outbox.dispatched_at = dispatched_at
        return self._outbox

    async def mark_outbox_failed(self, outbox_id, *, last_error, retryable):
        self._outbox.status = "pending" if retryable else "failed"
        self._outbox.locked_at = None
        self._outbox.last_error = last_error
        return self._outbox

    async def has_active_outbox(self, repo_sync_id):
        return self._outbox.status != "dispatched"

    async def update_state(self, *, repo_sync_id, status, last_error=None, last_synced_at=None):
        self.states.append(status)
        return self._repo_sync


class _DrainDocumentRepo:
    def __init__(self, document: "_DispatchDocument") -> None:
        self._document = document

    async def get_by_id(self, document_id):
        return self._document if document_id == self._document.id else None

    async def update(self, document):
        return None


class _DispatchDocument:
    def __init__(self, document_id: UUID, *, status: DocumentStatus = DocumentStatus.PENDING) -> None:
        self.id = document_id
        self.status = status
        self.queued = False

    def mark_queued(self) -> None:
        self.status = DocumentStatus.QUEUED
        self.queued = True


class _Outbox:
    def __init__(self, *, repo_sync_id: UUID, document_id: UUID, task_name: str) -> None:
        self.id = uuid4()
        self.repo_sync_id = repo_sync_id
        self.document_id = document_id
        self.task_name = task_name
        self.status = "pending"
        self.attempts = 0
        self.locked_at = None
        self.last_error = None
        self.dispatched_at = None
        self.created_at = datetime(2026, 5, 17, tzinfo=UTC)
        self.updated_at = None
