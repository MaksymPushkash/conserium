import uuid
from collections.abc import Mapping
from datetime import UTC, datetime
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from src.application.dtos.compare_dtos import CompareEvidenceRowDTO, CompareListDTO, CompareResultDTO
from src.application.dtos.query_dtos import QuerySourceDTO
from src.application.ports.auth.jwt_service import IJWTService
from src.application.ports.persistence.unit_of_work import IUnitOfWork
from src.application.use_cases.compare import (
    CompareDocumentsUseCase,
    DeleteCompareResultUseCase,
    GetCompareResultUseCase,
    ListCompareResultsUseCase,
)
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


class _ReturningCompareUseCase:
    def __init__(self, result: CompareResultDTO) -> None:
        self._result = result
        self.received: tuple[uuid.UUID, uuid.UUID, uuid.UUID] | None = None

    async def __call__(self, dto):
        self.received = (dto.user_id, dto.left_document_id, dto.right_document_id)
        return self._result


class _ReturningCompareListUseCase:
    def __init__(self, result: CompareListDTO) -> None:
        self._result = result

    async def __call__(self, dto):
        return self._result


class _ReturningCompareDetailUseCase:
    def __init__(self, result: CompareResultDTO) -> None:
        self._result = result

    async def __call__(self, dto):
        return self._result


class _DeletingCompareUseCase:
    async def __call__(self, dto):
        return None


def test_compare_documents_route_returns_markdown_and_sources() -> None:
    user = _make_user()
    left_document_id = uuid.uuid4()
    right_document_id = uuid.uuid4()
    source = QuerySourceDTO(
        chunk_id=uuid.uuid4(),
        document_id=left_document_id,
        document_title="FastAPI Notes",
        content="FastAPI focuses on API development.",
        page_number=None,
        chunk_index=0,
        score=0.9,
        used_in_answer=True,
    )
    use_case = _ReturningCompareUseCase(
        CompareResultDTO(
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
                CompareEvidenceRowDTO(
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
    app.state.dishka_container = _FakeRootContainer(
        {
            IJWTService: jwt_service,
            IUnitOfWork: _FakeUnitOfWork(user),
            CompareDocumentsUseCase: use_case,
        }
    )
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
    assert use_case.received == (user.id, left_document_id, right_document_id)


def test_compare_result_history_routes_return_persisted_results() -> None:
    user = _make_user()
    result = _compare_result(user_id=user.id)
    jwt_service = MagicMock()
    jwt_service.verify_access_token.return_value = user.id
    app = create_app()
    app.state.dishka_container = _FakeRootContainer(
        {
            IJWTService: jwt_service,
            IUnitOfWork: _FakeUnitOfWork(user),
            ListCompareResultsUseCase: _ReturningCompareListUseCase(CompareListDTO(items=[result], total=1)),
            GetCompareResultUseCase: _ReturningCompareDetailUseCase(result),
            DeleteCompareResultUseCase: _DeletingCompareUseCase(),
        }
    )
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


def _compare_result(*, user_id: uuid.UUID) -> CompareResultDTO:
    return CompareResultDTO(
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
