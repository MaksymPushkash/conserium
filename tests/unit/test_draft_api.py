import uuid
from collections.abc import Mapping
from datetime import UTC, datetime
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from src.application.dtos.draft_dtos import DraftResultDTO
from src.application.dtos.query_dtos import QuerySourceDTO
from src.application.ports.auth.jwt_service import IJWTService
from src.application.ports.persistence.unit_of_work import IUnitOfWork
from src.application.use_cases.drafts import GenerateDraftUseCase
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


class _ReturningDraftUseCase:
    def __init__(self, result: DraftResultDTO) -> None:
        self._result = result
        self.received_prompt: str | None = None

    async def __call__(self, dto):
        self.received_prompt = dto.prompt
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


def test_generate_draft_route_returns_markdown_and_sources() -> None:
    user = _make_user()
    document_id = uuid.uuid4()
    source = QuerySourceDTO(
        chunk_id=uuid.uuid4(),
        document_id=document_id,
        document_title="Python Notes",
        content="Generators yield values lazily.",
        page_number=None,
        chunk_index=0,
        score=0.9,
        used_in_answer=True,
    )
    use_case = _ReturningDraftUseCase(
        DraftResultDTO(
            prompt="Write about Python generators",
            markdown="# Python generators\n\nGenerators yield values lazily [1].",
            sources=[source],
            gaps=[],
        )
    )
    jwt_service = MagicMock()
    jwt_service.verify_access_token.return_value = user.id
    app = create_app()
    app.state.dishka_container = _FakeRootContainer(
        {
            IJWTService: jwt_service,
            IUnitOfWork: _FakeUnitOfWork(user),
            GenerateDraftUseCase: use_case,
        }
    )
    client = TestClient(app, raise_server_exceptions=False)

    try:
        response = client.post(
            "/api/v1/drafts/generate",
            headers={"Authorization": "Bearer access-token"},
            json={"prompt": "Write about Python generators", "limit": 8},
        )
    finally:
        client.close()

    assert response.status_code == 200
    assert response.json()["markdown"].startswith("# Python generators")
    assert response.json()["sources"][0]["document_id"] == str(document_id)
    assert response.json()["gaps"] == []
    assert use_case.received_prompt == "Write about Python generators"
