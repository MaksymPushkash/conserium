from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, cast

import pytest

from src.documents.ingestion import (
    DocumentIngester,
    TextDocumentIngester,
)
from src.documents.processing import DocumentProcessingService
from src.documents.text_chunker import SimpleTextChunker
from src.documents.types import DocumentType
from src.kit.exceptions import ValidationException
from src.models.collection import CollectionModel
from src.models.user import UserModel
from src.users.repository import UserRepository
from src.workspaces.repository import SharedWorkspaceRepository
from src.workspaces.schemas import WorkspaceAuditEventRecord, WorkspaceMemberRecord, WorkspaceRecord
from src.workspaces.service import WorkspaceService

if TYPE_CHECKING:
    from src.documents.document_repository import DocumentRepository
    from src.documents.service import DocumentCollectionAccess
    from src.documents.status_cache import RedisDocumentStatusCache
    from src.models.chunk import ChunkModel
    from src.models.document import DocumentModel
    from src.worker.dispatcher import CeleryTaskDispatcher


class _FakeUserRepository:
    def __init__(self, users: list[UserModel] | None = None) -> None:
        self._users = users or []

    async def get_by_email(self, email: str) -> UserModel | None:
        normalized = email.strip().lower()
        return next((user for user in self._users if user.email == normalized), None)

    async def get_by_id(self, user_id: uuid.UUID) -> UserModel | None:
        return next((user for user in self._users if user.id == user_id), None)


class _FakeCollectionRepository:
    def __init__(self, collection: CollectionModel | None = None) -> None:
        self.collection = collection

    async def get_by_id(self, collection_id: uuid.UUID) -> CollectionModel | None:
        if self.collection and self.collection.id == collection_id:
            return self.collection
        return None


class _FakeDocumentRepository:
    def __init__(self) -> None:
        self.created: list[DocumentModel] = []
        self.updated: list[DocumentModel] = []

    async def create(self, document: DocumentModel) -> None:
        self.created.append(document)

    async def update(self, document: DocumentModel) -> None:
        self.updated.append(document)


class _FakeDocumentActivityRepository:
    def __init__(self) -> None:
        self.events: list[tuple[uuid.UUID, uuid.UUID, str]] = []

    async def record_event(self, *, user_id: uuid.UUID, document_id: uuid.UUID, event_type: str) -> None:
        self.events.append((user_id, document_id, event_type))


class _FakeDocumentProcessingOutboxRepository:
    def __init__(self) -> None:
        self.created: list[tuple[uuid.UUID, str]] = []
        self.dispatched: list[uuid.UUID] = []

    async def create_outbox(self, *, document_id: uuid.UUID, task_name: str) -> object:
        self.created.append((document_id, task_name))
        return _OutboxRecord(id=uuid.uuid4())

    async def mark_dispatching(self, outbox_id: uuid.UUID, locked_at: object) -> object:
        return _OutboxRecord(id=outbox_id)

    async def mark_dispatched(self, outbox_id: uuid.UUID, dispatched_at: object) -> object:
        self.dispatched.append(outbox_id)
        return _OutboxRecord(id=outbox_id)


class _OutboxRecord:
    def __init__(self, id: uuid.UUID) -> None:
        self.id = id


class _FakeStatusCache:
    def __init__(self) -> None:
        self.calls: list[tuple[str, int, str]] = []

    async def set_status(self, document_id: uuid.UUID, status: str, progress: int, message: str) -> None:
        self.calls.append((status, progress, message))


class _FakeTaskDispatcher:
    def __init__(self) -> None:
        self.document_processing_outbox_dispatches = 0
        self.processed_document_ids: list[str] = []

    async def dispatch_document_processing_outbox(self) -> None:
        self.document_processing_outbox_dispatches += 1

    async def dispatch_process_document(self, document_id: str, *, task_id: str | None = None) -> None:
        self.processed_document_ids.append(document_id)


class _FakeChunkRepository:
    def __init__(self) -> None:
        self.created_batches: list[list[ChunkModel]] = []

    async def create_batch(self, chunks: list[ChunkModel]) -> None:
        self.created_batches.append(chunks)


class _FakeSharedWorkspaceRepository:
    def __init__(self, workspace: WorkspaceRecord, member: WorkspaceMemberRecord | None = None) -> None:
        self.workspace = workspace
        self.member = member
        self.force_stale_owner_transfer = False
        self.collection_audit_events: list[tuple[uuid.UUID, uuid.UUID, str, dict[str, object]]] = []
        self.workspace_audit_events: list[WorkspaceAuditEventRecord] = []
        self.removed_member_id: uuid.UUID | None = None
        self.archived_workspace_id: uuid.UUID | None = None
        self.upserted_workspace_members: list[tuple[uuid.UUID, str, str, uuid.UUID, uuid.UUID | None]] = []

    async def get_workspace(self, *, workspace_id: uuid.UUID) -> WorkspaceRecord | None:
        return self.workspace if self.workspace.id == workspace_id else None

    async def update_workspace(self, *, workspace_id: uuid.UUID, name: str, description: str | None) -> WorkspaceRecord | None:
        if self.workspace.id != workspace_id:
            return None
        self.workspace = WorkspaceRecord(
            id=self.workspace.id,
            user_id=self.workspace.user_id,
            name=name,
            description=description,
            access_role=self.workspace.access_role,
            created_at=self.workspace.created_at,
            updated_at=datetime.now(UTC),
        )
        return self.workspace

    async def archive_workspace(self, *, workspace_id: uuid.UUID) -> bool:
        if self.workspace.id != workspace_id:
            return False
        self.archived_workspace_id = workspace_id
        return True

    async def get_workspace_member_for_user(self, *, workspace_id: uuid.UUID, user_id: uuid.UUID) -> WorkspaceMemberRecord | None:
        if self.member and self.member.workspace_id == workspace_id and self.member.user_id == user_id:
            return self.member
        return None

    async def get_workspace_member(self, *, workspace_id: uuid.UUID, member_id: uuid.UUID) -> WorkspaceMemberRecord | None:
        if self.member and self.member.workspace_id == workspace_id and self.member.id == member_id:
            return self.member
        return None

    async def update_workspace_owner(self, *, workspace_id: uuid.UUID, user_id: uuid.UUID) -> WorkspaceRecord | None:
        if self.workspace.id != workspace_id:
            return None
        self.workspace = WorkspaceRecord(
            id=self.workspace.id,
            user_id=user_id,
            name=self.workspace.name,
            description=self.workspace.description,
            access_role="owner",
            created_at=self.workspace.created_at,
            updated_at=datetime.now(UTC),
        )
        return self.workspace

    async def transfer_workspace_owner_if_current(
        self,
        *,
        workspace_id: uuid.UUID,
        current_owner_user_id: uuid.UUID,
        new_owner_user_id: uuid.UUID,
    ) -> WorkspaceRecord | None:
        if self.force_stale_owner_transfer:
            return None
        if self.workspace.id != workspace_id or self.workspace.user_id != current_owner_user_id:
            return None
        self.workspace = WorkspaceRecord(
            id=self.workspace.id,
            user_id=new_owner_user_id,
            name=self.workspace.name,
            description=self.workspace.description,
            access_role="owner",
            created_at=self.workspace.created_at,
            updated_at=datetime.now(UTC),
        )
        return self.workspace

    async def upsert_workspace_member(
        self,
        *,
        workspace_id: uuid.UUID,
        email: str,
        role: str,
        invited_by_user_id: uuid.UUID,
        user_id: uuid.UUID | None,
    ) -> WorkspaceMemberRecord:
        self.upserted_workspace_members.append((workspace_id, email, role, invited_by_user_id, user_id))
        self.member = WorkspaceMemberRecord(
            id=uuid.uuid4(),
            workspace_id=workspace_id,
            user_id=user_id,
            email=email,
            role=role,
            invite_status="active" if user_id else "pending",
            invited_by_user_id=invited_by_user_id,
            created_at=datetime.now(UTC),
            updated_at=None,
        )
        return self.member

    async def update_workspace_member_role(self, *, member_id: uuid.UUID, role: str) -> WorkspaceMemberRecord | None:
        if self.member is None or self.member.id != member_id:
            return None
        self.member = WorkspaceMemberRecord(
            id=self.member.id,
            workspace_id=self.member.workspace_id,
            user_id=self.member.user_id,
            email=self.member.email,
            role=role,
            invite_status=self.member.invite_status,
            invited_by_user_id=self.member.invited_by_user_id,
            created_at=self.member.created_at,
            updated_at=datetime.now(UTC),
        )
        return self.member

    async def remove_workspace_member(self, *, member_id: uuid.UUID) -> bool:
        self.removed_member_id = member_id
        return True

    async def create_workspace_audit_event(
        self,
        *,
        workspace_id: uuid.UUID,
        actor_user_id: uuid.UUID,
        event_type: str,
        metadata: dict[str, object],
    ) -> WorkspaceAuditEventRecord:
        event = WorkspaceAuditEventRecord(
            id=uuid.uuid4(),
            workspace_id=workspace_id,
            actor_user_id=actor_user_id,
            event_type=event_type,
            metadata=metadata,
            created_at=datetime.now(UTC),
        )
        self.workspace_audit_events.append(event)
        return event

    async def create_audit_event(
        self,
        *,
        collection_id: uuid.UUID,
        actor_user_id: uuid.UUID,
        event_type: str,
        metadata: dict[str, object],
    ) -> None:
        self.collection_audit_events.append((collection_id, actor_user_id, event_type, metadata))


class _FakeRepositorySession:
    def __init__(self, *, workspace: WorkspaceRecord, member: WorkspaceMemberRecord | None = None, collection: CollectionModel | None = None, users: list[UserModel] | None = None) -> None:
        self.shared_workspace_repo = _FakeSharedWorkspaceRepository(workspace, member)
        self.collection_repo = _FakeCollectionRepository(collection)
        self.user_repo = _FakeUserRepository(users)
        self.document_repo = _FakeDocumentRepository()
        self.document_activity_repo = _FakeDocumentActivityRepository()
        self.document_processing_outbox_repo = _FakeDocumentProcessingOutboxRepository()
        self.chunk_repo = _FakeChunkRepository()
        self.commits = 0

    async def __aenter__(self) -> _FakeRepositorySession:
        return self

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None

    async def commit(self) -> None:
        self.commits += 1

    async def flush(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        return None


class _FakeDocumentCollectionAccess:
    def __init__(self, repository_session: _FakeRepositorySession) -> None:
        self._repository_session = repository_session

    async def document_owner_id(self, *, collection_id: uuid.UUID, user_id: uuid.UUID) -> uuid.UUID:
        collection = await self._repository_session.collection_repo.get_by_id(collection_id)
        if collection is None:
            raise AssertionError("collection not found")
        return collection.user_id if collection.workspace_id is not None else user_id

    async def record_shared_document_event(
        self,
        *,
        collection_id: uuid.UUID,
        actor_user_id: uuid.UUID,
        document_id: uuid.UUID,
        title: str,
    ) -> None:
        collection = await self._repository_session.collection_repo.get_by_id(collection_id)
        if collection is not None and collection.user_id != actor_user_id:
            await self._repository_session.shared_workspace_repo.create_audit_event(
                collection_id=collection_id,
                actor_user_id=actor_user_id,
                event_type="shared_ingestion",
                metadata={"document_id": str(document_id), "title": title},
            )


class _FakeSession:
    def __init__(self) -> None:
        self.commits = 0

    async def commit(self) -> None:
        self.commits += 1

    async def flush(self) -> None:
        self.commits += 1


def _patch_workspace_repositories(
    monkeypatch: pytest.MonkeyPatch,
    *,
    workspace_repo: _FakeSharedWorkspaceRepository,
    user_repo: _FakeUserRepository | None = None,
) -> None:
    monkeypatch.setattr(
        SharedWorkspaceRepository,
        "from_session",
        classmethod(lambda cls, session: workspace_repo),
    )
    monkeypatch.setattr(
        UserRepository,
        "from_session",
        classmethod(lambda cls, session: user_repo or _FakeUserRepository()),
    )


def _user(user_id: uuid.UUID, email: str) -> UserModel:
    return UserModel(
        id=user_id,
        email=email,
        password="hashed",
        display_name=email.split("@")[0],
        is_active=True,
        created_at=datetime.now(UTC),
        updated_at=None,
    )


def _workspace(owner_id: uuid.UUID, workspace_id: uuid.UUID | None = None) -> WorkspaceRecord:
    return WorkspaceRecord(
        id=workspace_id or uuid.uuid4(),
        user_id=owner_id,
        name="Research",
        description=None,
        access_role="owner",
        created_at=datetime.now(UTC),
        updated_at=None,
    )


def _member(workspace_id: uuid.UUID, user_id: uuid.UUID, role: str = "editor") -> WorkspaceMemberRecord:
    return WorkspaceMemberRecord(
        id=uuid.uuid4(),
        workspace_id=workspace_id,
        user_id=user_id,
        email="editor@example.com",
        role=role,
        invite_status="active",
        invited_by_user_id=uuid.uuid4(),
        created_at=datetime.now(UTC),
        updated_at=None,
    )


def _as_document_repository(repository_session: _FakeRepositorySession) -> DocumentRepository:
    return cast("DocumentRepository", repository_session.document_repo)


@pytest.mark.asyncio
async def test_workspace_member_invite_update_remove_writes_audit_events(monkeypatch: pytest.MonkeyPatch) -> None:
    owner_id = uuid.uuid4()
    workspace = _workspace(owner_id)
    repository = _FakeSharedWorkspaceRepository(workspace)
    session = _FakeSession()
    _patch_workspace_repositories(monkeypatch, workspace_repo=repository)
    service = WorkspaceService()

    invited = await service.invite_member(
        session,
        workspace_id=workspace.id,
        actor_user_id=owner_id,
        email=" NEW@Example.com ",
        role="editor",
    )
    updated = await service.update_member_role(
        session,
        workspace_id=workspace.id,
        member_id=invited.id,
        actor_user_id=owner_id,
        role="viewer",
    )
    await service.remove_member(session, workspace_id=workspace.id, member_id=invited.id, actor_user_id=owner_id)

    assert invited.email == "new@example.com"
    assert invited.invite_status == "pending"
    assert updated.role == "viewer"
    assert repository.removed_member_id == invited.id
    assert [event.event_type for event in repository.workspace_audit_events] == [
        "member_invited",
        "member_role_updated",
        "member_removed",
    ]
    assert session.commits == 3


@pytest.mark.asyncio
async def test_workspace_owner_updates_name_description_and_writes_audit_event(monkeypatch: pytest.MonkeyPatch) -> None:
    owner_id = uuid.uuid4()
    workspace = _workspace(owner_id)
    repository = _FakeSharedWorkspaceRepository(workspace)
    session = _FakeSession()
    _patch_workspace_repositories(monkeypatch, workspace_repo=repository)

    result = await WorkspaceService().update(
        session,
        workspace_id=workspace.id,
        actor_user_id=owner_id,
        name=" Updated team ",
        description=" New description ",
    )

    assert result.name == "Updated team"
    assert result.description == "New description"
    assert repository.workspace_audit_events[-1].event_type == "workspace_updated"
    assert session.commits == 1


@pytest.mark.asyncio
async def test_workspace_owner_archives_workspace_and_writes_audit_event(monkeypatch: pytest.MonkeyPatch) -> None:
    owner_id = uuid.uuid4()
    workspace = _workspace(owner_id)
    repository = _FakeSharedWorkspaceRepository(workspace)
    session = _FakeSession()
    _patch_workspace_repositories(monkeypatch, workspace_repo=repository)

    await WorkspaceService().delete(session, workspace_id=workspace.id, actor_user_id=owner_id)

    assert repository.archived_workspace_id == workspace.id
    assert repository.workspace_audit_events[-1].event_type == "workspace_archived"
    assert session.commits == 1


@pytest.mark.asyncio
async def test_workspace_owner_transfer_promotes_active_member_and_keeps_previous_owner_as_editor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner_id = uuid.uuid4()
    next_owner_id = uuid.uuid4()
    workspace = _workspace(owner_id)
    member = _member(workspace.id, next_owner_id, role="editor")
    repository = _FakeSharedWorkspaceRepository(workspace, member)
    user_repository = _FakeUserRepository([_user(owner_id, "owner@example.com"), _user(next_owner_id, "next@example.com")])
    session = _FakeSession()
    _patch_workspace_repositories(monkeypatch, workspace_repo=repository, user_repo=user_repository)

    result = await WorkspaceService().transfer_ownership(
        session,
        workspace_id=workspace.id,
        actor_user_id=owner_id,
        member_id=member.id,
    )

    assert result.user_id == next_owner_id
    assert repository.removed_member_id == member.id
    assert repository.upserted_workspace_members[-1] == (workspace.id, "owner@example.com", "editor", next_owner_id, owner_id)
    assert repository.workspace_audit_events[-1].event_type == "workspace_owner_transferred"
    assert session.commits == 1


@pytest.mark.asyncio
async def test_workspace_owner_transfer_rejects_stale_owner_update(monkeypatch: pytest.MonkeyPatch) -> None:
    owner_id = uuid.uuid4()
    next_owner_id = uuid.uuid4()
    workspace = _workspace(owner_id)
    member = _member(workspace.id, next_owner_id, role="editor")
    repository = _FakeSharedWorkspaceRepository(workspace, member)
    repository.force_stale_owner_transfer = True
    user_repository = _FakeUserRepository([_user(owner_id, "owner@example.com")])
    session = _FakeSession()
    _patch_workspace_repositories(monkeypatch, workspace_repo=repository, user_repo=user_repository)

    with pytest.raises(ValidationException, match="ownership changed"):
        await WorkspaceService().transfer_ownership(
            session,
            workspace_id=workspace.id,
            actor_user_id=owner_id,
            member_id=member.id,
        )

    assert repository.removed_member_id is None
    assert repository.upserted_workspace_members == []
    assert repository.workspace_audit_events == []
    assert session.commits == 0


@pytest.mark.asyncio
async def test_shared_text_ingestion_uses_workspace_owner_and_records_audit_event() -> None:
    owner_id = uuid.uuid4()
    editor_id = uuid.uuid4()
    workspace = _workspace(owner_id)
    member = _member(workspace.id, editor_id, role="editor")
    collection = CollectionModel.create(
        id=uuid.uuid4(),
        user_id=owner_id,
        workspace_id=workspace.id,
        name="Shared research",
    )
    repository_session = _FakeRepositorySession(workspace=workspace, member=member, collection=collection)

    result = await TextDocumentIngester(
        repository_session,  # type: ignore[arg-type]
        _as_document_repository(repository_session),
        SimpleTextChunker(max_chunk_chars=80),
        cast("DocumentCollectionAccess", _FakeDocumentCollectionAccess(repository_session)),
        repository_session.chunk_repo,
    )(
        user_id=editor_id,
        title="Shared note",
        raw_text="Shared workspace ingestion should be audited.",
        collection_id=collection.id,
    )

    assert result.user_id == owner_id
    assert repository_session.document_repo.created[0].user_id == owner_id
    assert repository_session.shared_workspace_repo.collection_audit_events == [
        (
            collection.id,
            editor_id,
            "shared_ingestion",
            {"document_id": str(result.id), "title": "Shared note"},
        )
    ]



@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("document_type", "file_path"),
    [(DocumentType.PDF, "/tmp/shared.pdf"), (DocumentType.IMAGE, "/tmp/shared.png")],
)
async def test_shared_file_ingestion_uses_workspace_owner_and_records_audit_event(document_type: DocumentType, file_path: str) -> None:
    owner_id = uuid.uuid4()
    editor_id = uuid.uuid4()
    workspace = _workspace(owner_id)
    member = _member(workspace.id, editor_id, role="editor")
    collection = CollectionModel.create(
        id=uuid.uuid4(),
        user_id=owner_id,
        workspace_id=workspace.id,
        name="Shared uploads",
    )
    repository_session = _FakeRepositorySession(workspace=workspace, member=member, collection=collection)
    dispatcher = _FakeTaskDispatcher()
    status_cache = _FakeStatusCache()

    result = await DocumentIngester(
        repository_session,  # type: ignore[arg-type]
        _as_document_repository(repository_session),
        cast("RedisDocumentStatusCache", status_cache),
        cast("CeleryTaskDispatcher", dispatcher),
        cast("DocumentCollectionAccess", _FakeDocumentCollectionAccess(repository_session)),
        repository_session.document_activity_repo,
        DocumentProcessingService(
            repository_session,  # type: ignore[arg-type]
            repository_session.document_repo,  # type: ignore[arg-type]
            repository_session.document_processing_outbox_repo,  # type: ignore[arg-type]
            cast("RedisDocumentStatusCache", status_cache),
            cast("CeleryTaskDispatcher", dispatcher),
        ),
    )(
        user_id=editor_id,
        title=f"Shared {document_type.value}",
        type=document_type,
        collection_id=collection.id,
        file_path=file_path,
        file_size_bytes=128,
    )

    assert result.user_id == owner_id
    assert repository_session.document_repo.created[0].user_id == owner_id
    assert repository_session.document_repo.created[0].file_path == file_path
    assert repository_session.document_activity_repo.events[0][0] == owner_id
    assert repository_session.document_processing_outbox_repo.created == [(result.id, "process_document")]
    assert dispatcher.document_processing_outbox_dispatches == 0
    assert dispatcher.processed_document_ids == []
    assert repository_session.shared_workspace_repo.collection_audit_events == [
        (
            collection.id,
            editor_id,
            "shared_ingestion",
            {"document_id": str(result.id), "title": f"Shared {document_type.value}"},
        )
    ]
