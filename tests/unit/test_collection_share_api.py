import uuid
from collections.abc import Mapping
from datetime import UTC, datetime
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from src.auth.jwt_service import JWTService
from src.collections.endpoints import get_collection_share_service
from src.collections.service import to_collection_share_response
from src.documents.status import DocumentStatus
from src.documents.types import DocumentType
from src.main import create_app
from src.models.user import UserModel
from src.postgres import get_db_read_session, get_db_session
from src.public_shares.dependencies import get_public_query_graph_runner
from src.public_shares.endpoints import get_public_share_service
from src.public_shares.schemas import (
    AnswerShareRecord,
    AnswerShareSource,
    CollectionShareRecord,
    PublicCollectionDocument,
    PublicCollectionResult,
)
from src.public_shares.service import (
    to_answer_share_list_response,
    to_public_answer_share_response,
    to_public_collection_response,
    to_public_query_source_response,
)
from src.query.schemas import PublicCollectionQueryResponse, QuerySource
from src.users.repository import UserRepository
from tests.dependency_overrides import apply_dependency_overrides


class _FakeRequestContainer:
    def __init__(self, dependencies: Mapping[type[object], object]) -> None:
        self._dependencies = dependencies

    async def get(self, type_hint: type[object], component: str = "") -> object:
        return self._dependencies[type_hint]


class _FakeScopeContext:
    def __init__(self, dependencies: Mapping[type[object], object]) -> None:
        self._request_container = _FakeRequestContainer(dependencies)

    async def __aenter__(self) -> _FakeRequestContainer:
        return self._request_container

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None


class _FakeDependencyContainer:
    def __init__(self, dependencies: Mapping[type[object], object]) -> None:
        self._dependencies = dependencies

    def __call__(self, context: object, scope: object) -> _FakeScopeContext:
        return _FakeScopeContext(self._dependencies)


class _FakeUserRepository:
    def __init__(self, user: UserModel) -> None:
        self._user = user

    async def get_by_id(self, user_id: uuid.UUID) -> UserModel | None:
        return self._user


class _FakeRepositorySession:
    def __init__(self, user: UserModel) -> None:
        self.user_repo = _FakeUserRepository(user)

    async def __aenter__(self) -> "_FakeRepositorySession":
        return self

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None


class _ReturningCreateShareService:
    def __init__(self, share: CollectionShareRecord) -> None:
        self._share = share
        self.received: tuple[uuid.UUID, uuid.UUID] | None = None

    async def create_share(self, session: object, *, user_id: uuid.UUID, collection_id: uuid.UUID):
        self.received = (user_id, collection_id)
        return to_collection_share_response(self._share)


class _ReturningPublicCollectionService:
    def __init__(self, collection: PublicCollectionResult) -> None:
        self._collection = collection
        self.received: str | None = None

    async def get_public_collection(self, session: object, *, slug: str):
        self.received = slug
        return to_public_collection_response(self._collection)


class _ReturningPublicCollectionQueryService:
    def __init__(self, result: PublicCollectionQueryResponse) -> None:
        self._result = result
        self.received: tuple[str, str, int] | None = None

    async def query_public_collection(
        self,
        *,
        graph_runner: object,
        slug: str,
        query: str,
        client_key: str,
        limit: int,
    ) -> PublicCollectionQueryResponse:
        self.received = (slug, query, limit)
        return self._result


class _ReturningPublicAnswerShareService:
    def __init__(self, share: AnswerShareRecord) -> None:
        self._share = share
        self.received: str | None = None

    async def get_public_answer_share(self, session: object, *, slug: str):
        self.received = slug
        return to_public_answer_share_response(self._share)


class _ReturningListAnswerSharesService:
    def __init__(self, shares: list[AnswerShareRecord]) -> None:
        self._shares = shares
        self.received: tuple[uuid.UUID, int, int] | None = None

    async def list_answer_shares(self, session: object, *, user_id: uuid.UUID, limit: int = 50, offset: int = 0):
        self.received = (user_id, limit, offset)
        return to_answer_share_list_response(self._shares)


class _RecordingRevokeAnswerShareService:
    def __init__(self) -> None:
        self.received: tuple[uuid.UUID, str] | None = None

    async def revoke_answer_share(self, session: object, *, user_id: uuid.UUID, slug: str) -> None:
        self.received = (user_id, slug)


def _dependency_override(handler: object):
    def override() -> object:
        return handler

    return override


async def _session_override():
    yield object()


def _graph_runner_override() -> object:
    return object()


def test_create_collection_share_route_returns_slug() -> None:
    user = _make_user()
    collection_id = uuid.uuid4()
    share = CollectionShareRecord(
        id=uuid.uuid4(),
        collection_id=collection_id,
        user_id=user.id,
        slug="public-slug",
        include_summaries=True,
        include_notes=False,
        ask_enabled=True,
        daily_ask_limit=100,
        revoked_at=None,
        created_at=datetime.now(UTC),
        updated_at=None,
    )
    handler = _ReturningCreateShareService(share)
    jwt_service = MagicMock()
    jwt_service.verify_access_token.return_value = user.id
    app = create_app()
    apply_dependency_overrides(app, _FakeDependencyContainer(
        {
            JWTService: jwt_service,
            UserRepository: _FakeRepositorySession(user),
        }
    )._dependencies)
    app.dependency_overrides[get_collection_share_service] = _dependency_override(handler)
    app.dependency_overrides[get_db_session] = _session_override
    client = TestClient(app, raise_server_exceptions=False)

    try:
        response = client.post(
            f"/api/v1/collections/{collection_id}/share",
            headers={"Authorization": "Bearer access-token"},
        )
    finally:
        client.close()

    assert response.status_code == 201
    assert response.json()["slug"] == "public-slug"
    assert "user_id" not in response.json()
    assert handler.received == (user.id, collection_id)


def test_public_collection_route_returns_no_private_user_fields() -> None:
    collection = PublicCollectionResult(
        id=uuid.uuid4(),
        name="Python",
        description="Python material",
        color="#ffffff",
        documents=[
            PublicCollectionDocument(
                id=uuid.uuid4(),
                title="Async Python",
                type=DocumentType.TEXT,
                status=DocumentStatus.READY,
                source_url="https://example.com/python",
                summary="Short summary.",
                word_count=120,
                language="en",
                tags=["python"],
                created_at=datetime.now(UTC),
                updated_at=None,
            )
        ],
        created_at=datetime.now(UTC),
        updated_at=None,
    )
    handler = _ReturningPublicCollectionService(collection)
    app = create_app()
    apply_dependency_overrides(app, _FakeDependencyContainer({})._dependencies)
    app.dependency_overrides[get_public_share_service] = _dependency_override(handler)
    app.dependency_overrides[get_db_read_session] = _session_override
    client = TestClient(app, raise_server_exceptions=False)

    try:
        response = client.get("/api/v1/public/collections/public-slug")
    finally:
        client.close()

    assert response.status_code == 200
    payload = response.json()
    assert payload["name"] == "Python"
    assert payload["documents"][0]["summary"] == "Short summary."
    assert "user_id" not in payload
    assert "raw_content" not in payload["documents"][0]
    assert handler.received == "public-slug"


def _make_user() -> UserModel:
    return UserModel(
        id=uuid.uuid4(),
        email="user@example.com",
        password="$2b$12$hashedpassword",
        display_name="Test User",
        is_active=True,
        created_at=datetime.now(UTC),
        updated_at=None,
    )


def test_public_collection_query_returns_share_slug() -> None:
    source = QuerySource(
        chunk_id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        document_title="Clean Architecture",
        content="Policy does not depend on details.",
        page_number=4,
        chunk_index=1,
        score=0.7,
        used_in_answer=True,
    )
    share_source = AnswerShareSource(
        chunk_id=source.chunk_id,
        document_id=source.document_id,
        document_title=source.document_title,
        content=source.content,
        page_number=source.page_number,
        chunk_index=source.chunk_index,
        citation="[1]",
        used_in_answer=True,
    )
    answer_share = AnswerShareRecord(
        id=uuid.uuid4(),
        slug="answer-slug",
        user_id=uuid.uuid4(),
        collection_id=uuid.uuid4(),
        collection_name="Architecture",
        conversation_id=uuid.uuid4(),
        public_collection_slug="public-slug",
        query_text="What matters?",
        answer_text="Policy stays independent [1].",
        sources=[share_source],
        revoked_at=None,
        created_at=datetime.now(UTC),
        updated_at=None,
    )
    result = PublicCollectionQueryResponse.model_validate(
        {
            "query": "What matters?",
            "answer": "Policy stays independent [1].",
            "sources": [to_public_query_source_response(source, 1).model_dump()],
            "share": to_public_answer_share_response(answer_share).model_dump(),
        }
    )
    handler = _ReturningPublicCollectionQueryService(result)
    app = create_app()
    apply_dependency_overrides(app, _FakeDependencyContainer({})._dependencies)
    app.dependency_overrides[get_public_share_service] = _dependency_override(handler)
    app.dependency_overrides[get_db_session] = _session_override
    app.dependency_overrides[get_public_query_graph_runner] = _graph_runner_override
    client = TestClient(app, raise_server_exceptions=False)

    try:
        response = client.post("/api/v1/public/collections/public-slug/query", json={"query": "What matters?", "limit": 6})
    finally:
        client.close()

    assert response.status_code == 200
    payload = response.json()
    assert payload["answer"] == "Policy stays independent [1]."
    assert payload["share"]["slug"] == "answer-slug"
    assert "conversation_id" not in payload
    assert "debug" not in payload
    assert "refrag_context" not in payload
    assert "chunk_id" not in payload["sources"][0]
    assert "document_id" not in payload["sources"][0]
    assert payload["share"]["url_path"] == "/public/answers/answer-slug"
    assert payload["share"]["sources"][0]["citation"] == "[1]"
    assert "collection_id" not in payload["share"]
    assert "chunk_id" not in payload["share"]["sources"][0]
    assert "document_id" not in payload["share"]["sources"][0]
    assert handler.received == ("public-slug", "What matters?", 6)


def test_public_answer_share_route_returns_citations() -> None:
    source = AnswerShareSource(
        chunk_id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        document_title="Clean Architecture",
        content="Policy does not depend on details.",
        page_number=4,
        chunk_index=1,
        citation="[1]",
        used_in_answer=True,
    )
    share = AnswerShareRecord(
        id=uuid.uuid4(),
        slug="answer-slug",
        user_id=uuid.uuid4(),
        collection_id=uuid.uuid4(),
        collection_name="Architecture",
        conversation_id=uuid.uuid4(),
        public_collection_slug="public-slug",
        query_text="What matters?",
        answer_text="Policy stays independent [1].",
        sources=[source],
        revoked_at=None,
        created_at=datetime.now(UTC),
        updated_at=None,
    )
    handler = _ReturningPublicAnswerShareService(share)
    app = create_app()
    apply_dependency_overrides(app, _FakeDependencyContainer({})._dependencies)
    app.dependency_overrides[get_public_share_service] = _dependency_override(handler)
    app.dependency_overrides[get_db_read_session] = _session_override
    client = TestClient(app, raise_server_exceptions=False)

    try:
        response = client.get("/api/v1/public/answers/answer-slug")
    finally:
        client.close()

    assert response.status_code == 200
    payload = response.json()
    assert payload["query"] == "What matters?"
    assert payload["sources"][0]["document_title"] == "Clean Architecture"
    assert "user_id" not in payload
    assert "collection_id" not in payload
    assert "chunk_id" not in payload["sources"][0]
    assert "document_id" not in payload["sources"][0]
    assert handler.received == "answer-slug"


def test_list_answer_shares_route_returns_owner_shares() -> None:
    user = _make_user()
    share = AnswerShareRecord(
        id=uuid.uuid4(),
        slug="answer-slug",
        user_id=user.id,
        collection_id=uuid.uuid4(),
        collection_name="Architecture",
        conversation_id=None,
        public_collection_slug="public-slug",
        query_text="What matters?",
        answer_text="Policy stays independent [1].",
        sources=[],
        revoked_at=None,
        created_at=datetime.now(UTC),
        updated_at=None,
    )
    handler = _ReturningListAnswerSharesService([share])
    jwt_service = MagicMock()
    jwt_service.verify_access_token.return_value = user.id
    app = create_app()
    apply_dependency_overrides(app, _FakeDependencyContainer(
        {
            JWTService: jwt_service,
            UserRepository: _FakeRepositorySession(user),
        }
    )._dependencies)
    app.dependency_overrides[get_public_share_service] = _dependency_override(handler)
    app.dependency_overrides[get_db_read_session] = _session_override
    client = TestClient(app, raise_server_exceptions=False)

    try:
        response = client.get("/api/v1/answer-shares?limit=10", headers={"Authorization": "Bearer access-token"})
    finally:
        client.close()

    assert response.status_code == 200
    payload = response.json()
    assert payload["items"][0]["slug"] == "answer-slug"
    assert payload["items"][0]["collection_id"] == str(share.collection_id)
    assert handler.received == (user.id, 10, 0)


def test_revoke_answer_share_route_revokes_owner_share() -> None:
    user = _make_user()
    handler = _RecordingRevokeAnswerShareService()
    jwt_service = MagicMock()
    jwt_service.verify_access_token.return_value = user.id
    app = create_app()
    apply_dependency_overrides(app, _FakeDependencyContainer(
        {
            JWTService: jwt_service,
            UserRepository: _FakeRepositorySession(user),
        }
    )._dependencies)
    app.dependency_overrides[get_public_share_service] = _dependency_override(handler)
    app.dependency_overrides[get_db_session] = _session_override
    client = TestClient(app, raise_server_exceptions=False)

    try:
        response = client.delete("/api/v1/answer-shares/answer-slug", headers={"Authorization": "Bearer access-token"})
    finally:
        client.close()

    assert response.status_code == 204
    assert handler.received == (user.id, "answer-slug")
