import uuid
from collections.abc import Mapping
from datetime import UTC, datetime
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from src.application.dtos.review_dtos import FlashcardDTO, FlashcardListDTO, GenerateFlashcardsResultDTO
from src.application.ports.auth.jwt_service import IJWTService
from src.application.ports.persistence.unit_of_work import IUnitOfWork
from src.application.use_cases.review import GenerateFlashcardsUseCase, ListDueFlashcardsUseCase, ReviewFlashcardUseCase
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
    def __init__(self, result: object) -> None:
        self._result = result
        self.received_args: tuple[object, ...] = ()
        self.received_kwargs: dict[str, object] = {}

    async def __call__(self, *args: object, **kwargs: object) -> object:
        self.received_args = args
        self.received_kwargs = kwargs
        return self._result


def test_generate_flashcards_route_returns_created_cards() -> None:
    user = _make_user()
    card = _flashcard(user.id)
    use_case = _ReturningUseCase(GenerateFlashcardsResultDTO(items=[card], created_count=1))
    client = _make_client(user, {GenerateFlashcardsUseCase: use_case})

    try:
        response = client.post(
            "/api/v1/review/flashcards/generate",
            headers={"Authorization": "Bearer access-token"},
            json={"document_id": str(card.source_document_id), "limit": 5},
        )
    finally:
        client.close()

    assert response.status_code == 201
    assert response.json()["created_count"] == 1
    assert response.json()["items"][0]["question"] == "What is asyncio?"
    assert use_case.received_args


def test_due_flashcards_route_returns_due_cards() -> None:
    user = _make_user()
    card = _flashcard(user.id)
    use_case = _ReturningUseCase(FlashcardListDTO(items=[card], total=1, limit=10))
    client = _make_client(user, {ListDueFlashcardsUseCase: use_case})

    try:
        response = client.get("/api/v1/review/flashcards/due?limit=10", headers={"Authorization": "Bearer access-token"})
    finally:
        client.close()

    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert response.json()["items"][0]["id"] == str(card.id)
    assert use_case.received_kwargs == {"user_id": user.id, "limit": 10}


def test_review_flashcard_route_returns_updated_card() -> None:
    user = _make_user()
    card = _flashcard(user.id)
    use_case = _ReturningUseCase(card)
    client = _make_client(user, {ReviewFlashcardUseCase: use_case})

    try:
        response = client.post(
            f"/api/v1/review/flashcards/{card.id}/review",
            headers={"Authorization": "Bearer access-token"},
            json={"grade": "good"},
        )
    finally:
        client.close()

    assert response.status_code == 200
    assert response.json()["id"] == str(card.id)
    assert use_case.received_args


def _make_client(user: UserEntity, dependencies: Mapping[type[object], object]) -> TestClient:
    jwt_service = MagicMock()
    jwt_service.verify_access_token.return_value = user.id
    app = create_app()
    app.state.dishka_container = _FakeRootContainer(
        {
            IJWTService: jwt_service,
            IUnitOfWork: _FakeUnitOfWork(user),
            **dependencies,
        }
    )
    return TestClient(app, raise_server_exceptions=False)


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


def _flashcard(user_id: uuid.UUID) -> FlashcardDTO:
    now = datetime.now(UTC)
    return FlashcardDTO(
        id=uuid.uuid4(),
        user_id=user_id,
        scope_type="document",
        collection_id=None,
        topic=None,
        source_document_id=uuid.uuid4(),
        source_chunk_id=None,
        question="What is asyncio?",
        answer="Asyncio runs cooperative I/O.",
        citation_metadata={},
        due_at=now,
        interval_days=0,
        ease_factor=2.5,
        review_count=0,
        source_title="Asyncio notes",
        created_at=now,
        updated_at=None,
    )
