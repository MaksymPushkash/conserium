import uuid
from collections.abc import Mapping
from datetime import UTC, datetime
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from src.auth.jwt_service import JWTServiceProtocol
from src.knowledge_graph.schemas import (
    KnowledgeGraphDTO,
    KnowledgeGraphEdgeDTO,
    KnowledgeGraphInsightDTO,
    KnowledgeGraphInsightsDTO,
    KnowledgeGraphInsightsResponse,
    KnowledgeGraphNodeDTO,
    KnowledgeGraphResponse,
)
from src.knowledge_graph.service import (
    KnowledgeGraphFilters,
    get_knowledge_graph_service,
    to_knowledge_graph_insights_response,
    to_knowledge_graph_response,
)
from src.main import create_app
from src.models.user import UserModel
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


class _ReturningKnowledgeGraphService:
    def __init__(self, result: KnowledgeGraphDTO) -> None:
        self._result = to_knowledge_graph_response(result)
        self.received: dict[str, object] | None = None

    async def get_graph(
        self,
        *,
        user_id: uuid.UUID,
        filters: KnowledgeGraphFilters,
    ) -> KnowledgeGraphResponse:
        self.received = {
            "user_id": user_id,
            "document_limit": filters.document_limit,
            "topic_limit": filters.topic_limit,
            "collection_id": filters.collection_id,
            "tag_name": filters.tag_name,
            "topic_name": filters.topic_name,
            "document_type": filters.document_type,
            "recency_days": filters.recency_days,
        }
        return self._result


class _ReturningKnowledgeGraphInsightsService:
    def __init__(self, result: KnowledgeGraphInsightsDTO) -> None:
        self._result = to_knowledge_graph_insights_response(result)
        self.received: dict[str, object] | None = None

    async def get_insights(
        self,
        *,
        user_id: uuid.UUID,
        filters: KnowledgeGraphFilters,
    ) -> KnowledgeGraphInsightsResponse:
        self.received = {
            "user_id": user_id,
            "document_limit": filters.document_limit,
            "topic_limit": filters.topic_limit,
            "collection_id": filters.collection_id,
            "tag_name": filters.tag_name,
            "topic_name": filters.topic_name,
            "document_type": filters.document_type,
            "recency_days": filters.recency_days,
        }
        return self._result


def test_get_knowledge_graph_route_returns_nodes_and_edges() -> None:
    user = _make_user()
    service = _ReturningKnowledgeGraphService(
        KnowledgeGraphDTO(
            nodes=[
                KnowledgeGraphNodeDTO(id="topic:python", kind="topic", label="python"),
                KnowledgeGraphNodeDTO(
                    id="document:1",
                    kind="document",
                    label="FastAPI Notes",
                    detail="TEXT",
                    summary="FastAPI summary",
                    suggested_questions=["How does FastAPI work?"],
                ),
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
    apply_dependency_overrides(app, _FakeDependencyContainer(
        {
            JWTServiceProtocol: jwt_service,
            UserRepository: _FakeRepositorySession(user),
        }
    )._dependencies)
    app.dependency_overrides[get_knowledge_graph_service] = lambda: service
    client = TestClient(app, raise_server_exceptions=False)

    try:
        response = client.get(
            "/api/v1/knowledge-graph?document_limit=50&topic_limit=10&tag=python&topic=api&document_type=TEXT&recency_days=30",
            headers={"Authorization": "Bearer access-token"},
        )
    finally:
        client.close()

    assert response.status_code == 200
    assert response.json()["nodes"][0]["id"] == "topic:python"
    assert response.json()["nodes"][1]["summary"] == "FastAPI summary"
    assert response.json()["edges"][0]["relation_type"] == "same_topic"
    assert service.received is not None
    assert service.received["user_id"] == user.id
    assert service.received["document_limit"] == 50
    assert service.received["topic_limit"] == 10
    assert service.received["tag_name"] == "python"
    assert service.received["topic_name"] == "api"
    assert service.received["recency_days"] == 30


def test_get_knowledge_graph_insights_route_returns_backend_signals() -> None:
    user = _make_user()
    service = _ReturningKnowledgeGraphInsightsService(
        KnowledgeGraphInsightsDTO(
            items=[
                KnowledgeGraphInsightDTO(
                    kind="pinned_topics",
                    title="Pinned topics",
                    description="Topics manually marked as important.",
                    severity="info",
                    count=1,
                    nodes=[KnowledgeGraphNodeDTO(id="topic:python", kind="topic", label="python", is_pinned=True)],
                )
            ]
        )
    )
    jwt_service = MagicMock()
    jwt_service.verify_access_token.return_value = user.id
    app = create_app()
    apply_dependency_overrides(app, _FakeDependencyContainer(
        {
            JWTServiceProtocol: jwt_service,
            UserRepository: _FakeRepositorySession(user),
        }
    )._dependencies)
    app.dependency_overrides[get_knowledge_graph_service] = lambda: service
    client = TestClient(app, raise_server_exceptions=False)

    try:
        response = client.get(
            "/api/v1/knowledge-graph/insights?document_limit=70&topic_limit=30&topic=python",
            headers={"Authorization": "Bearer access-token"},
        )
    finally:
        client.close()

    assert response.status_code == 200
    assert response.json()["items"][0]["kind"] == "pinned_topics"
    assert response.json()["items"][0]["nodes"][0]["is_pinned"] is True
    assert service.received is not None
    assert service.received["user_id"] == user.id
    assert service.received["document_limit"] == 70
    assert service.received["topic_limit"] == 30
    assert service.received["topic_name"] == "python"


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
