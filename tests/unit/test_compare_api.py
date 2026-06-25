import uuid
from collections.abc import Mapping
from datetime import UTC, datetime
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from src.auth.jwt_service import JWTService
from src.compare.dependencies import get_compare_llm_service, get_compare_query_executor, get_compare_service
from src.compare.schemas import CompareEvidence, CompareListResult, CompareResult
from src.compare.service import (
    to_compare_documents_response,
    to_compare_list_response,
)
from src.main import create_app
from src.models.user import UserModel
from src.postgres import get_db_read_session, get_db_session
from src.query.schemas import QuerySource
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


class _ReturningCompareService:
    def __init__(self, result: CompareResult) -> None:
        self._result = result
        self.received: tuple[uuid.UUID, uuid.UUID, uuid.UUID] | None = None

    async def compare_documents(self, session, *, query_executor, llm_service, user_id, body):
        self.received = (user_id, body.left_document_id, body.right_document_id)
        return to_compare_documents_response(self._result)


class _ReturningCompareHistoryService:
    def __init__(self, result: CompareResult) -> None:
        self._result = result

    async def list_results(self, session, **kwargs):
        return to_compare_list_response(CompareListResult(items=[self._result], total=1))

    async def get_result(self, session, **kwargs):
        return to_compare_documents_response(self._result)

    async def delete_result(self, session, **kwargs):
        return None


async def _session_override():
    yield object()


def _dependency_override(dependency: object):
    def override() -> object:
        return dependency

    return override


def test_compare_documents_route_returns_markdown_and_sources() -> None:
    user = _make_user()
    left_document_id = uuid.uuid4()
    right_document_id = uuid.uuid4()
    source = QuerySource(
        chunk_id=uuid.uuid4(),
        document_id=left_document_id,
        document_title="FastAPI Notes",
        content="FastAPI focuses on API development.",
        page_number=None,
        chunk_index=0,
        score=0.9,
        used_in_answer=True,
    )
    handler = _ReturningCompareService(
        CompareResult(
            id=uuid.uuid4(),
            user_id=user.id,
            collection_id=None,
            left_document_id=left_document_id,
            right_document_id=right_document_id,
            left_title="FastAPI Notes",
            right_title="Django Notes",
            dimensions=["claims", "tradeoffs"],
            markdown="## Shared ideas\n\nBoth discuss Python web work [1].",
            summary="FastAPI Notes vs Django Notes.",
            evidence_rows=[
                CompareEvidence(
                    dimension="claims",
                    left_evidence="FastAPI focuses on API development.",
                    right_evidence=None,
                    assessment="Claims have evidence from the left document only.",
                )
            ],
            sources=[source],
            created_at=datetime.now(UTC),
        )
    )
    jwt_service = MagicMock()
    jwt_service.verify_access_token.return_value = user.id
    app = create_app()
    apply_dependency_overrides(app, _FakeDependencyContainer(
        {
            JWTService: jwt_service,
            UserRepository: _FakeRepositorySession(user),
        }
    )._dependencies)
    app.dependency_overrides[get_compare_service] = _dependency_override(handler)
    app.dependency_overrides[get_db_session] = _session_override
    app.dependency_overrides[get_compare_query_executor] = _dependency_override(object())
    app.dependency_overrides[get_compare_llm_service] = _dependency_override(object())
    client = TestClient(app, raise_server_exceptions=False)

    try:
        response = client.post(
            "/api/v1/compare/documents",
            headers={"Authorization": "Bearer access-token"},
            json={
                "left_document_id": str(left_document_id),
                "right_document_id": str(right_document_id),
                "prompt": "focus on routing",
            },
        )
    finally:
        client.close()

    assert response.status_code == 200
    assert response.json()["left_title"] == "FastAPI Notes"
    assert response.json()["right_title"] == "Django Notes"
    assert response.json()["markdown"].startswith("## Shared ideas")
    assert response.json()["dimensions"] == ["claims", "tradeoffs"]
    assert response.json()["evidence_rows"][0]["dimension"] == "claims"
    assert response.json()["sources"][0]["document_id"] == str(left_document_id)
    assert handler.received == (user.id, left_document_id, right_document_id)


def test_compare_result_history_routes_return_persisted_results() -> None:
    user = _make_user()
    result = _compare_result(user_id=user.id)
    jwt_service = MagicMock()
    jwt_service.verify_access_token.return_value = user.id
    app = create_app()
    apply_dependency_overrides(app, _FakeDependencyContainer(
        {
            JWTService: jwt_service,
            UserRepository: _FakeRepositorySession(user),
        }
    )._dependencies)
    app.dependency_overrides[get_db_read_session] = _session_override
    app.dependency_overrides[get_db_session] = _session_override
    app.dependency_overrides[get_compare_service] = _dependency_override(_ReturningCompareHistoryService(result))
    client = TestClient(app, raise_server_exceptions=False)

    try:
        list_response = client.get("/api/v1/compare/results", headers={"Authorization": "Bearer access-token"})
        get_response = client.get(f"/api/v1/compare/results/{result.id}", headers={"Authorization": "Bearer access-token"})
        delete_response = client.delete(f"/api/v1/compare/results/{result.id}", headers={"Authorization": "Bearer access-token"})
    finally:
        client.close()

    assert list_response.status_code == 200
    assert list_response.json()["items"][0]["id"] == str(result.id)
    assert get_response.status_code == 200
    assert get_response.json()["id"] == str(result.id)
    assert delete_response.status_code == 204


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


def _compare_result(*, user_id: uuid.UUID) -> CompareResult:
    return CompareResult(
        id=uuid.uuid4(),
        user_id=user_id,
        collection_id=None,
        left_document_id=uuid.uuid4(),
        right_document_id=uuid.uuid4(),
        left_title="Left",
        right_title="Right",
        dimensions=["claims"],
        markdown="## Summary",
        summary="Left vs Right.",
        evidence_rows=[],
        sources=[],
        created_at=datetime.now(UTC),
    )
