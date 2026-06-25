import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest

from src.collections.repository import CollectionRepository
from src.collections.service import CollectionShareService
from src.documents.status import DocumentStatus
from src.documents.types import DocumentType
from src.kit.exceptions import ResourceNotFoundException
from src.models.collection import CollectionModel
from src.postgres import AsyncSession
from src.public_shares.repository import AnswerShareRepository, CollectionShareRepository
from src.public_shares.schemas import (
    AnswerShareRecord,
    AnswerShareSource,
    CollectionShareRecord,
    PublicCollectionDocument,
    PublicCollectionResult,
)
from src.public_shares.service import PublicAskLedger, PublicShareService
from src.query.agents.state import ConseriumQueryState
from src.query.schemas import QuerySource, RefragContextPackage

if TYPE_CHECKING:
    from pytest import MonkeyPatch


class _FakeCollectionRepository:
    def __init__(self, collection: CollectionModel | None) -> None:
        self.collection = collection

    async def get_by_id(self, collection_id: uuid.UUID) -> CollectionModel | None:
        return self.collection if self.collection and self.collection.id == collection_id else None


class _FakeCollectionShareRepository:
    def __init__(self) -> None:
        self.share: CollectionShareRecord | None = None
        self.public_collection: PublicCollectionResult | None = None
        self.revoked: tuple[uuid.UUID, uuid.UUID] | None = None
        self.events: dict[uuid.UUID, dict[str, object]] = {}
        self.locked_scope: tuple[uuid.UUID, str] | None = None

    async def get_active_by_collection_id(
        self,
        *,
        user_id: uuid.UUID,
        collection_id: uuid.UUID,
    ) -> CollectionShareRecord | None:
        if self.share and self.share.user_id == user_id and self.share.collection_id == collection_id:
            return self.share
        return None

    async def get_active_by_slug(self, slug: str) -> CollectionShareRecord | None:
        if self.share and self.share.slug == slug:
            return self.share
        return None

    async def lock_public_ask_scope(
        self,
        *,
        owner_user_id: uuid.UUID,
        share_slug: str,
    ) -> CollectionShareRecord | None:
        self.locked_scope = (owner_user_id, share_slug)
        return await self.get_active_by_slug(share_slug)

    async def create(
        self,
        *,
        id: uuid.UUID,
        collection_id: uuid.UUID,
        user_id: uuid.UUID,
        slug: str,
        include_summaries: bool,
        include_notes: bool,
    ) -> CollectionShareRecord:
        self.share = CollectionShareRecord(
            id=id,
            collection_id=collection_id,
            user_id=user_id,
            slug=slug,
            include_summaries=include_summaries,
            include_notes=include_notes,
            ask_enabled=True,
            daily_ask_limit=100,
            revoked_at=None,
            created_at=datetime.now(UTC),
            updated_at=None,
        )
        return self.share

    async def revoke_by_collection_id(
        self,
        *,
        user_id: uuid.UUID,
        collection_id: uuid.UUID,
        revoked_at: datetime,
    ) -> bool:
        self.revoked = (user_id, collection_id)
        if self.share:
            self.share = CollectionShareRecord(
                id=self.share.id,
                collection_id=self.share.collection_id,
                user_id=self.share.user_id,
                slug=self.share.slug,
                include_summaries=self.share.include_summaries,
                include_notes=self.share.include_notes,
                ask_enabled=self.share.ask_enabled,
                daily_ask_limit=self.share.daily_ask_limit,
                revoked_at=revoked_at,
                created_at=self.share.created_at,
                updated_at=self.share.updated_at,
            )
        return True

    async def update_public_ask_settings(
        self,
        *,
        user_id: uuid.UUID,
        collection_id: uuid.UUID,
        ask_enabled: bool | None,
        daily_ask_limit: int | None,
    ) -> CollectionShareRecord | None:
        if not self.share or self.share.user_id != user_id or self.share.collection_id != collection_id:
            return None
        self.share = CollectionShareRecord(
            id=self.share.id,
            collection_id=self.share.collection_id,
            user_id=self.share.user_id,
            slug=self.share.slug,
            include_summaries=self.share.include_summaries,
            include_notes=self.share.include_notes,
            ask_enabled=self.share.ask_enabled if ask_enabled is None else ask_enabled,
            daily_ask_limit=self.share.daily_ask_limit if daily_ask_limit is None else daily_ask_limit,
            revoked_at=self.share.revoked_at,
            created_at=self.share.created_at,
            updated_at=self.share.updated_at,
        )
        return self.share

    async def count_public_ask_events_by_share(self, *, share_slug: str, since: datetime) -> int:
        return 0

    async def count_public_ask_events_by_owner(self, *, owner_user_id: uuid.UUID, since: datetime) -> int:
        return 0

    async def record_public_ask_event(
        self,
        *,
        id: uuid.UUID,
        share_slug: str,
        collection_share_id: uuid.UUID | None,
        owner_user_id: uuid.UUID,
        client_key: str,
        status: str,
        reason: str | None,
        query_text: str,
        answer_share_slug: str | None,
    ) -> None:
        self.events[id] = {
            "status": status,
            "reason": reason,
            "answer_share_slug": answer_share_slug,
        }

    async def update_public_ask_event(
        self,
        *,
        event_id: uuid.UUID,
        status: str,
        reason: str | None,
        answer_share_slug: str | None = None,
    ) -> None:
        self.events[event_id] = {
            "status": status,
            "reason": reason,
            "answer_share_slug": answer_share_slug,
        }

    async def get_public_collection(self, slug: str) -> PublicCollectionResult | None:
        if self.share and self.share.slug == slug and self.share.revoked_at is None:
            return self.public_collection
        return None


class _FakeAnswerShareRepository:
    def __init__(self) -> None:
        self.share: AnswerShareRecord | None = None

    async def get_active_by_slug(self, slug: str) -> AnswerShareRecord | None:
        if self.share and self.share.slug == slug:
            return self.share
        return None

    async def list_by_user_id(self, *, user_id: uuid.UUID, limit: int, offset: int) -> list[AnswerShareRecord]:
        if self.share and self.share.user_id == user_id:
            return [self.share]
        return []

    async def count_recent_by_public_collection_slug(self, *, slug: str, since: datetime) -> int:
        return int(self.share is not None and self.share.public_collection_slug == slug and self.share.created_at >= since)

    async def revoke_by_slug(self, *, user_id: uuid.UUID, slug: str, revoked_at: datetime) -> bool:
        return bool(self.share and self.share.user_id == user_id and self.share.slug == slug)

    async def create(
        self,
        *,
        id: uuid.UUID,
        slug: str,
        user_id: uuid.UUID,
        collection_id: uuid.UUID | None,
        conversation_id: uuid.UUID | None,
        public_collection_slug: str | None,
        query_text: str,
        answer_text: str,
        sources: list[AnswerShareSource],
    ) -> AnswerShareRecord:
        self.share = AnswerShareRecord(
            id=id,
            slug=slug,
            user_id=user_id,
            collection_id=collection_id,
            collection_name=None,
            conversation_id=conversation_id,
            public_collection_slug=public_collection_slug,
            query_text=query_text,
            answer_text=answer_text,
            sources=sources,
            revoked_at=None,
            created_at=datetime.now(UTC),
            updated_at=None,
        )
        return self.share


class _FakeSession:
    committed: bool = False
    commit_count: int = 0

    async def flush(self) -> None:
        self.committed = True

    async def commit(self) -> None:
        self.committed = True
        self.commit_count += 1

    async def __aenter__(self) -> "_FakeSession":
        return self

    async def __aexit__(self, exc_type: object, exc_value: object, traceback: object) -> None:
        return None

    async def rollback(self) -> None:
        return None


class _Repositories:
    def __init__(self, collection: CollectionModel | None) -> None:
        self.collection_repo = _FakeCollectionRepository(collection)
        self.collection_share_repo = _FakeCollectionShareRepository()
        self.answer_share_repo = _FakeAnswerShareRepository()


@pytest.mark.asyncio
async def test_create_collection_share_returns_active_share(monkeypatch: "MonkeyPatch") -> None:
    user_id = uuid.uuid4()
    collection = _make_collection(user_id)
    session, _ = _wire_repositories(monkeypatch, collection)

    share = await CollectionShareService().create_share(session, user_id=user_id, collection_id=collection.id)

    assert share.collection_id == collection.id
    assert share.include_summaries is True
    assert share.include_notes is False
    assert session.committed is True


@pytest.mark.asyncio
async def test_create_collection_share_rejects_non_owner(monkeypatch: "MonkeyPatch") -> None:
    collection = _make_collection(uuid.uuid4())
    session, _ = _wire_repositories(monkeypatch, collection)

    with pytest.raises(ResourceNotFoundException):
        await CollectionShareService().create_share(session, user_id=uuid.uuid4(), collection_id=collection.id)


@pytest.mark.asyncio
async def test_revoke_collection_share_marks_active_share_revoked(monkeypatch: "MonkeyPatch") -> None:
    user_id = uuid.uuid4()
    collection = _make_collection(user_id)
    session, repositories = _wire_repositories(monkeypatch, collection)
    service = CollectionShareService()

    await service.create_share(session, user_id=user_id, collection_id=collection.id)
    await service.revoke_share(session, user_id=user_id, collection_id=collection.id)

    assert repositories.collection_share_repo.revoked == (user_id, collection.id)


@pytest.mark.asyncio
async def test_public_collection_returns_shared_documents(monkeypatch: "MonkeyPatch") -> None:
    user_id = uuid.uuid4()
    collection = _make_collection(user_id)
    session, repositories = _wire_repositories(monkeypatch, collection)
    share = await CollectionShareService().create_share(session, user_id=user_id, collection_id=collection.id)
    repositories.collection_share_repo.public_collection = PublicCollectionResult(
        id=collection.id,
        name=collection.name,
        description=collection.description,
        color=collection.color,
        documents=[
            PublicCollectionDocument(
                id=uuid.uuid4(),
                title="Async Python",
                type=DocumentType.TEXT,
                status=DocumentStatus.READY,
                source_url=None,
                summary="Async summary.",
                word_count=120,
                language="en",
                tags=["python"],
                created_at=datetime.now(UTC),
                updated_at=None,
            )
        ],
        created_at=collection.created_at,
        updated_at=collection.updated_at,
    )

    result = await PublicShareService().get_public_collection(session, slug=share.slug)

    assert result.name == "Python"
    assert result.documents[0].summary == "Async summary."


def _make_collection(user_id: uuid.UUID) -> CollectionModel:
    return CollectionModel.create(
        id=uuid.uuid4(),
        user_id=user_id,
        name="Python",
        description="Python material",
        color="#ffffff",
    )


class _ReturningGraphRunner:
    def __init__(self, source: QuerySource) -> None:
        self.source = source
        self.received: ConseriumQueryState | None = None

    async def run(self, state: ConseriumQueryState) -> ConseriumQueryState:
        self.received = state
        state.answer = "Use dependency inversion [1]."
        state.sources = [self.source]
        state.refrag_context = RefragContextPackage(
            query=state.query,
            full_text_chunks=[],
            compressed_chunks=[],
            discarded_chunks=[],
            total_original_tokens=0,
            total_context_tokens=0,
            compression_strategy="none",
        )
        return state


class _FailingGraphRunner:
    async def run(self, state: ConseriumQueryState) -> ConseriumQueryState:
        raise RuntimeError("query failed")


@pytest.mark.asyncio
async def test_public_collection_query_persists_shareable_answer(monkeypatch: "MonkeyPatch") -> None:
    user_id = uuid.uuid4()
    collection = _make_collection(user_id)
    session, repositories = _wire_repositories(monkeypatch, collection)
    share = await CollectionShareService().create_share(session, user_id=user_id, collection_id=collection.id)
    source = QuerySource(
        chunk_id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        document_title="Clean Architecture",
        content="Dependency inversion keeps policy independent.",
        page_number=3,
        chunk_index=0,
        score=0.42,
        used_in_answer=True,
    )
    graph_runner = _ReturningGraphRunner(source)

    service = PublicShareService(PublicAskLedger(lambda: session))  # type: ignore[arg-type]
    result = await service.create_public_collection_query_result(
        graph_runner=graph_runner,  # type: ignore[arg-type]
        slug=share.slug,
        query="What matters?",
        client_key="test-client",
        limit=20,
    )

    assert graph_runner.received is not None
    assert graph_runner.received.collection_id == collection.id
    assert graph_runner.received.limit == 8
    assert graph_runner.received.conversation_turns == []
    assert result.share.query_text == "What matters?"
    assert result.share.answer_text == "Use dependency inversion [1]."
    assert result.share.public_collection_slug == share.slug
    assert result.share.conversation_id is None
    assert result.share.sources[0].citation == "[1]"
    assert result.share.sources[0].document_title == "Clean Architecture"
    assert repositories.collection_share_repo.locked_scope == (user_id, share.slug)
    assert len(repositories.collection_share_repo.events) == 1
    event = next(iter(repositories.collection_share_repo.events.values()))
    assert event == {"status": "allowed", "reason": None, "answer_share_slug": result.share.slug}
    assert session.commit_count == 2


@pytest.mark.asyncio
async def test_public_collection_query_failure_persists_failed_reservation(monkeypatch: "MonkeyPatch") -> None:
    user_id = uuid.uuid4()
    collection = _make_collection(user_id)
    session, repositories = _wire_repositories(monkeypatch, collection)
    share = await CollectionShareService().create_share(session, user_id=user_id, collection_id=collection.id)
    service = PublicShareService(PublicAskLedger(lambda: session))  # type: ignore[arg-type]

    with pytest.raises(RuntimeError, match="query failed"):
        await service.create_public_collection_query_result(
            graph_runner=_FailingGraphRunner(),  # type: ignore[arg-type]
            slug=share.slug,
            query="What matters?",
            client_key="test-client",
            limit=8,
        )

    event = next(iter(repositories.collection_share_repo.events.values()))
    assert event == {"status": "failed", "reason": "query_failed", "answer_share_slug": None}
    assert session.commit_count == 2


def _wire_repositories(monkeypatch: "MonkeyPatch", collection: CollectionModel | None) -> tuple[AsyncSession, _Repositories]:
    repositories = _Repositories(collection)
    monkeypatch.setattr(CollectionRepository, "from_session", classmethod(lambda cls, session: repositories.collection_repo))
    monkeypatch.setattr(
        CollectionShareRepository,
        "from_session",
        classmethod(lambda cls, session: repositories.collection_share_repo),
    )
    monkeypatch.setattr(
        AnswerShareRepository,
        "from_session",
        classmethod(lambda cls, session: repositories.answer_share_repo),
    )
    return _FakeSession(), repositories  # type: ignore[return-value]
