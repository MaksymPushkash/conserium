import uuid
from collections.abc import Mapping
from datetime import UTC, datetime
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from src.auth.jwt_service import JWTServiceProtocol
from src.conflicts.schemas import (
    ConflictDetectionResultDTO,
    ConflictDocumentDTO,
    ConflictFindingDTO,
)
from src.conflicts.service import get_conflict_llm_service, get_conflict_service, to_conflict_detection_response
from src.main import create_app
from src.models.user import UserModel
from src.postgres import get_db_session
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


class _ReturningConflictService:
    def __init__(self, result: ConflictDetectionResultDTO) -> None:
        self._result = result
        self.received_user_id: uuid.UUID | None = None

    async def detect(self, session, *, dto, llm_service):
        self.received_user_id = dto.user_id
        return to_conflict_detection_response(self._result)


async def _session_override():
    yield object()


def _dependency_override(dependency: object):
    def override() -> object:
        return dependency

    return override


def test_detect_conflicts_route_serializes_response() -> None:
    user = _make_user()
    document_id = uuid.uuid4()
    handler = _ReturningConflictService(
        ConflictDetectionResultDTO(
            collection_id=None,
            analyzed_document_count=2,
            conflicts=[
                ConflictFindingDTO(
                    subject="Typing",
                    summary="Saved materials contain opposing guidance about typing.",
                    documents=[ConflictDocumentDTO(id=document_id, title="Typing Notes")],
                    evidence=["Use type hints.", "Avoid type hints."],
                    score=0.7,
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
    app.dependency_overrides[get_conflict_service] = _dependency_override(handler)
    app.dependency_overrides[get_conflict_llm_service] = _dependency_override(object())
    app.dependency_overrides[get_db_session] = _session_override
    client = TestClient(app, raise_server_exceptions=False)

    try:
        response = client.get("/api/v1/conflicts", headers={"Authorization": "Bearer access-token"})
    finally:
        client.close()

    assert response.status_code == 200
    assert response.json()["conflicts"][0]["documents"][0]["id"] == str(document_id)
    assert handler.received_user_id == user.id


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
