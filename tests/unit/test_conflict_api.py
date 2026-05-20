import uuid
from collections.abc import Mapping
from datetime import UTC, datetime
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from src.application.dtos.conflict_dtos import (
    ConflictDetectionResultDTO,
    ConflictDocumentDTO,
    ConflictFindingDTO,
)
from src.application.ports.auth.jwt_service import IJWTService
from src.application.ports.persistence.unit_of_work import IUnitOfWork
from src.application.use_cases.conflicts import DetectConflictsUseCase
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


class _ReturningConflictUseCase:
    def __init__(self, result: ConflictDetectionResultDTO) -> None:
        self._result = result
        self.received_user_id: uuid.UUID | None = None

    async def __call__(self, dto):
        self.received_user_id = dto.user_id
        return self._result


def test_detect_conflicts_route_serializes_response() -> None:
    user = _make_user()
    document_id = uuid.uuid4()
    use_case = _ReturningConflictUseCase(
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
    app.state.dishka_container = _FakeRootContainer(
        {
            IJWTService: jwt_service,
            IUnitOfWork: _FakeUnitOfWork(user),
            DetectConflictsUseCase: use_case,
        }
    )
    client = TestClient(app, raise_server_exceptions=False)

    try:
        response = client.get("/api/v1/conflicts", headers={"Authorization": "Bearer access-token"})
    finally:
        client.close()

    assert response.status_code == 200
    assert response.json()["conflicts"][0]["documents"][0]["id"] == str(document_id)
    assert use_case.received_user_id == user.id


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
