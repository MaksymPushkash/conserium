import uuid
from collections.abc import Mapping
from datetime import UTC, datetime
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from src.application.dtos.topic_dtos import TopicDetailDTO, TopicDocumentDTO, TopicDTO, TopicListDTO
from src.application.ports.auth.jwt_service import IJWTService
from src.application.ports.persistence.unit_of_work import IUnitOfWork
from src.application.use_cases.topics import GetTopicDetailUseCase, ListTopicsUseCase
from src.domain.entities.user_entity import UserEntity
from src.domain.value_objects.email import Email
from src.main import create_app


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


class _FakeRootContainer:
    def __init__(self, dependencies: Mapping[type[object], object]) -> None:
        self._dependencies = dependencies

    def __call__(self, context: object, scope: object) -> _FakeScopeContext:
        return _FakeScopeContext(self._dependencies)


class _FakeUserRepository:
    def __init__(self, user: UserEntity) -> None:
        self._user = user

    async def get_by_id(self, user_id: uuid.UUID) -> UserEntity | None:
        return self._user


class _FakeUnitOfWork:
    def __init__(self, user: UserEntity) -> None:
        self.user_repo = _FakeUserRepository(user)

    async def __aenter__(self) -> "_FakeUnitOfWork":
        return self

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None


class _ReturningUseCase:
    def __init__(self, result: TopicListDTO) -> None:
        self._result = result
        self.received: tuple[uuid.UUID, int, int] | None = None

    async def __call__(self, *, user_id: uuid.UUID, limit: int = 50, offset: int = 0) -> TopicListDTO:
        self.received = (user_id, limit, offset)
        return self._result


class _ReturningDetailUseCase:
    def __init__(self, result: TopicDetailDTO) -> None:
        self._result = result
        self.received: tuple[uuid.UUID, str, int] | None = None

    async def __call__(self, *, user_id: uuid.UUID, name: str, document_limit: int = 10) -> TopicDetailDTO:
        self.received = (user_id, name, document_limit)
        return self._result


def _make_user() -> UserEntity:
    return UserEntity(
        id=uuid.uuid4(),
        email=Email(value="user@example.com"),
        password="$2b$12$hashedpassword",
        display_name="Test User",
        is_active=True,
        created_at=datetime.now(UTC),
        updated_at=None,
    )


def test_list_topics_route_returns_topic_groups() -> None:
    user = _make_user()
    use_case = _ReturningUseCase(
        TopicListDTO(
            items=[TopicDTO(name="python", document_count=3, last_document_at=datetime(2026, 5, 1, tzinfo=UTC))],
            total=1,
            limit=20,
            offset=0,
        )
    )
    jwt_service = MagicMock()
    jwt_service.verify_access_token.return_value = user.id
    app = create_app()
    app.state.dishka_container = _FakeRootContainer(
        {
            IJWTService: jwt_service,
            IUnitOfWork: _FakeUnitOfWork(user),
            ListTopicsUseCase: use_case,
        }
    )
    client = TestClient(app, raise_server_exceptions=False)

    try:
        response = client.get("/api/v1/topics?limit=20&offset=0", headers={"Authorization": "Bearer access-token"})
    finally:
        client.close()

    assert response.status_code == 200
    assert response.json()["items"][0]["name"] == "python"
    assert response.json()["items"][0]["document_count"] == 3
    assert response.json()["total"] == 1
    assert use_case.received == (user.id, 20, 0)


def test_get_topic_detail_route_returns_representative_documents() -> None:
    user = _make_user()
    document_id = uuid.uuid4()
    use_case = _ReturningDetailUseCase(
        TopicDetailDTO(
            topic=TopicDTO(name="python", document_count=1, last_document_at=datetime(2026, 5, 1, tzinfo=UTC)),
            documents=[
                TopicDocumentDTO(
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
    jwt_service = MagicMock()
    jwt_service.verify_access_token.return_value = user.id
    app = create_app()
    app.state.dishka_container = _FakeRootContainer(
        {
            IJWTService: jwt_service,
            IUnitOfWork: _FakeUnitOfWork(user),
            GetTopicDetailUseCase: use_case,
        }
    )
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
    assert use_case.received == (user.id, "python", 12)
