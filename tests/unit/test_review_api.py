import uuid
from collections.abc import Mapping
from datetime import UTC, datetime
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from src.auth.jwt_service import JWTService
from src.main import create_app
from src.models.user import UserModel
from src.review.dependencies import get_review_service
from src.review.schemas import (
    FlashcardListResponse,
    FlashcardResponse,
    GenerateFlashcardsResponse,
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


class _ReturningReviewService:
    def __init__(self, result: FlashcardListResponse | FlashcardResponse | GenerateFlashcardsResponse) -> None:
        self._result = result
        self.received_args: tuple[object, ...] = ()
        self.received_kwargs: dict[str, object] = {}

    async def generate_flashcards(self, *args: object, **kwargs: object) -> GenerateFlashcardsResponse:
        self.received_args = args
        self.received_kwargs = kwargs
        assert isinstance(self._result, GenerateFlashcardsResponse)
        return self._result

    async def list_due_flashcards(self, *args: object, **kwargs: object) -> FlashcardListResponse:
        self.received_args = args
        self.received_kwargs = kwargs
        assert isinstance(self._result, FlashcardListResponse)
        return self._result

    async def review_flashcard(self, *args: object, **kwargs: object) -> FlashcardResponse:
        self.received_args = args
        self.received_kwargs = kwargs
        assert isinstance(self._result, FlashcardResponse)
        return self._result


def test_generate_flashcards_route_returns_created_cards() -> None:
    user = _make_user()
    card = _flashcard(user.id)
    service = _ReturningReviewService(GenerateFlashcardsResponse(items=[card], created_count=1))
    client = _make_client(user, service)

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
    assert service.received_args


def test_due_flashcards_route_returns_due_cards() -> None:
    user = _make_user()
    card = _flashcard(user.id)
    service = _ReturningReviewService(FlashcardListResponse(items=[card], total=1, limit=10))
    client = _make_client(user, service)

    try:
        response = client.get("/api/v1/review/flashcards/due?limit=10", headers={"Authorization": "Bearer access-token"})
    finally:
        client.close()

    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert response.json()["items"][0]["id"] == str(card.id)
    assert service.received_args == (user.id,)
    assert service.received_kwargs == {"limit": 10}


def test_review_flashcard_route_returns_updated_card() -> None:
    user = _make_user()
    card = _flashcard(user.id)
    service = _ReturningReviewService(card)
    client = _make_client(user, service)

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
    assert service.received_args


def _make_client(user: UserModel, service: _ReturningReviewService) -> TestClient:
    jwt_service = MagicMock()
    jwt_service.verify_access_token.return_value = user.id
    app = create_app()
    apply_dependency_overrides(app, _FakeDependencyContainer(
        {
            JWTService: jwt_service,
            UserRepository: _FakeRepositorySession(user),
        }
    )._dependencies)
    app.dependency_overrides[get_review_service] = lambda: service
    return TestClient(app, raise_server_exceptions=False)


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


def _flashcard(user_id: uuid.UUID) -> FlashcardResponse:
    now = datetime.now(UTC)
    return FlashcardResponse(
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
