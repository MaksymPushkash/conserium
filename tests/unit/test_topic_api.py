import uuid
from collections.abc import Mapping
from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from src.auth.jwt_service import JWTServiceProtocol
from src.main import create_app
from src.models.user import UserModel
from src.topics.schemas import (
    TopicDetailResponse,
    TopicDocumentResponse,
    TopicListResponse,
    TopicResponse,
)
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


class _ReturningTopicListService:
    def __init__(self, result: TopicListResponse) -> None:
        self._result = result
        self.received: tuple[uuid.UUID, int, int] | None = None

    async def list_topics(self, session: object, *, user_id: uuid.UUID, limit: int, offset: int) -> TopicListResponse:
        self.received = (user_id, limit, offset)
        return self._result


class _ReturningTopicDetailService:
    def __init__(self, result: TopicDetailResponse) -> None:
        self._result = result
        self.received: tuple[uuid.UUID, str, int] | None = None

    async def get_detail(
        self,
        session: object,
        *,
        user_id: uuid.UUID,
        name: str,
        document_limit: int,
    ) -> TopicDetailResponse:
        self.received = (user_id, name, document_limit)
        return self._result


class _ReturningTopicManagementService:
    def __init__(self, result: TopicResponse, ignored_result: TopicResponse | None = None) -> None:
        self._result = result
        self._ignored_result = ignored_result or result
        self.received: dict[str, object] = {}

    async def rename(self, session: object, **kwargs: object) -> TopicResponse:
        self.received = kwargs
        return self._result

    async def merge(self, session: object, **kwargs: object) -> TopicResponse:
        self.received = kwargs
        return self._result

    async def pin(self, session: object, **kwargs: object) -> TopicResponse:
        self.received = kwargs
        return self._result

    async def ignore(self, session: object, **kwargs: object) -> TopicResponse:
        self.received = kwargs
        return self._ignored_result


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


async def _fake_session() -> object:
    yield object()


def _set_topics_service(monkeypatch: pytest.MonkeyPatch, service: object) -> None:
    import src.topics.endpoints as topic_endpoints

    monkeypatch.setattr(topic_endpoints, "topics", service)


def _override_sessions(app: object) -> None:
    from fastapi import FastAPI

    from src.postgres import get_db_read_session, get_db_session

    assert isinstance(app, FastAPI)
    app.dependency_overrides[get_db_read_session] = _fake_session
    app.dependency_overrides[get_db_session] = _fake_session


def test_list_topics_route_returns_topic_groups(monkeypatch: pytest.MonkeyPatch) -> None:
    user = _make_user()
    service = _ReturningTopicListService(
        TopicListResponse(
            items=[TopicResponse(name="python", document_count=3, last_document_at=datetime(2026, 5, 1, tzinfo=UTC))],
            total=1,
            limit=20,
            offset=0,
        )
    )
    _set_topics_service(monkeypatch, service)
    jwt_service = MagicMock()
    jwt_service.verify_access_token.return_value = user.id
    app = create_app()
    _override_sessions(app)
    apply_dependency_overrides(app, _FakeDependencyContainer(
        {
            JWTServiceProtocol: jwt_service,
            UserRepository: _FakeRepositorySession(user),
        }
    )._dependencies)
    client = TestClient(app, raise_server_exceptions=False)

    try:
        response = client.get("/api/v1/topics?limit=20&offset=0", headers={"Authorization": "Bearer access-token"})
    finally:
        client.close()

    assert response.status_code == 200
    assert response.json()["items"][0]["name"] == "python"
    assert response.json()["items"][0]["document_count"] == 3
    assert response.json()["total"] == 1
    assert service.received == (user.id, 20, 0)


def test_get_topic_detail_route_returns_representative_documents(monkeypatch: pytest.MonkeyPatch) -> None:
    user = _make_user()
    document_id = uuid.uuid4()
    service = _ReturningTopicDetailService(
        TopicDetailResponse(
            topic=TopicResponse(name="python", document_count=1, last_document_at=datetime(2026, 5, 1, tzinfo=UTC)),
            documents=[
                TopicDocumentResponse(
                    id=str(document_id),
                    title="Python Async",
                    type="TEXT",
                    status="READY",
                    summary="Async Python notes.",
                    created_at=datetime(2026, 5, 1, tzinfo=UTC),
                )
            ],
        )
    )
    _set_topics_service(monkeypatch, service)
    jwt_service = MagicMock()
    jwt_service.verify_access_token.return_value = user.id
    app = create_app()
    _override_sessions(app)
    apply_dependency_overrides(app, _FakeDependencyContainer(
        {
            JWTServiceProtocol: jwt_service,
            UserRepository: _FakeRepositorySession(user),
        }
    )._dependencies)
    client = TestClient(app, raise_server_exceptions=False)

    try:
        response = client.get(
            "/api/v1/topics/python?document_limit=12",
            headers={"Authorization": "Bearer access-token"},
        )
    finally:
        client.close()

    assert response.status_code == 200
    assert response.json()["topic"]["name"] == "python"
    assert response.json()["documents"][0]["id"] == str(document_id)
    assert response.json()["documents"][0]["title"] == "Python Async"
    assert service.received == (user.id, "python", 12)


def test_topic_management_routes_forward_authenticated_user_and_payloads(monkeypatch: pytest.MonkeyPatch) -> None:
    user = _make_user()
    service = _ReturningTopicManagementService(
        TopicResponse(
            name="Backend",
            document_count=2,
            last_document_at=datetime(2026, 5, 1, tzinfo=UTC),
            source_names=["python", "fastapi"],
            pinned=True,
        ),
        ignored_result=TopicResponse(name="Backend", document_count=2, last_document_at=None, ignored=True),
    )
    _set_topics_service(monkeypatch, service)
    jwt_service = MagicMock()
    jwt_service.verify_access_token.return_value = user.id
    app = create_app()
    _override_sessions(app)
    apply_dependency_overrides(app, _FakeDependencyContainer(
        {
            JWTServiceProtocol: jwt_service,
            UserRepository: _FakeRepositorySession(user),
        }
    )._dependencies)
    client = TestClient(app, raise_server_exceptions=False)

    try:
        rename_response = client.patch(
            "/api/v1/topics/python",
            json={"display_name": "Backend"},
            headers={"Authorization": "Bearer access-token"},
        )
        merge_response = client.post(
            "/api/v1/topics/Backend/merge",
            json={"source_names": ["python", "fastapi"]},
            headers={"Authorization": "Bearer access-token"},
        )
        pin_response = client.post(
            "/api/v1/topics/Backend/pin",
            json={"pinned": False},
            headers={"Authorization": "Bearer access-token"},
        )
        ignore_response = client.post(
            "/api/v1/topics/Backend/ignore",
            json={"ignored": True},
            headers={"Authorization": "Bearer access-token"},
        )
    finally:
        client.close()

    assert rename_response.status_code == 200
    assert rename_response.json()["source_names"] == ["python", "fastapi"]
    assert merge_response.status_code == 200
    assert pin_response.status_code == 200
    assert ignore_response.status_code == 200
    assert service.received == {"user_id": user.id, "name": "Backend", "ignored": True}
