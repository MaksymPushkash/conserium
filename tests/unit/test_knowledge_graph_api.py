import uuid
from collections.abc import Mapping
from datetime import UTC, datetime
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from src.application.dtos.knowledge_graph_dtos import KnowledgeGraphDTO, KnowledgeGraphEdgeDTO, KnowledgeGraphNodeDTO
from src.application.ports.auth.jwt_service import IJWTService
from src.application.ports.persistence.unit_of_work import IUnitOfWork
from src.application.use_cases.knowledge_graph import GetKnowledgeGraphUseCase
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


class _ReturningGraphUseCase:
    def __init__(self, result: KnowledgeGraphDTO) -> None:
        self._result = result
        self.received: tuple[uuid.UUID, int, int] | None = None

    async def __call__(self, *, user_id: uuid.UUID, document_limit: int = 80, topic_limit: int = 20) -> KnowledgeGraphDTO:
        self.received = (user_id, document_limit, topic_limit)
        return self._result


def test_get_knowledge_graph_route_returns_nodes_and_edges() -> None:
    user = _make_user()
    use_case = _ReturningGraphUseCase(
        KnowledgeGraphDTO(
            nodes=[
                KnowledgeGraphNodeDTO(id="topic:python", kind="topic", label="python"),
                KnowledgeGraphNodeDTO(id="document:1", kind="document", label="FastAPI Notes", detail="TEXT"),
            ],
            edges=[
                KnowledgeGraphEdgeDTO(
                    id="topic:python:document:1",
                    source_id="topic:python",
                    target_id="document:1",
                    relation_type="same_topic",
                    label="same topic",
                    score=1.0,
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
            GetKnowledgeGraphUseCase: use_case,
        }
    )
    client = TestClient(app, raise_server_exceptions=False)

    try:
        response = client.get(
            "/api/v1/knowledge-graph?document_limit=50&topic_limit=10",
            headers={"Authorization": "Bearer access-token"},
        )
    finally:
        client.close()

    assert response.status_code == 200
    assert response.json()["nodes"][0]["id"] == "topic:python"
    assert response.json()["edges"][0]["relation_type"] == "same_topic"
    assert use_case.received == (user.id, 50, 10)


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
