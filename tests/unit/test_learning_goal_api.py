import uuid
from collections.abc import Mapping
from datetime import UTC, datetime
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from src.auth.jwt_service import JWTService
from src.learning_goals.schemas import LearningGoalResult
from src.learning_goals.service import get_learning_goal_service, to_learning_goal_response
from src.main import create_app
from src.models.user import UserModel
from src.postgres import get_db_read_session
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


class _ReturningLearningGoalService:
    def __init__(self, result: list[LearningGoalResult]) -> None:
        self._result = result
        self.received_user_id: uuid.UUID | None = None

    async def list_goals(self, session: object, *, user_id: uuid.UUID):
        self.received_user_id = user_id
        return [to_learning_goal_response(goal) for goal in self._result]


async def _session_override():
    yield object()


def test_list_learning_goals_route_serializes_response() -> None:
    user = _make_user()
    goal_id = uuid.uuid4()
    now = datetime.now(UTC)
    service = _ReturningLearningGoalService(
        [
            LearningGoalResult(
                id=goal_id,
                user_id=user.id,
                topic="Python",
                description="Learn core Python",
                target_date=None,
                status="active",
                progress_ratio=0.5,
                covered_count=3,
                missing_count=3,
                gaps=[],
                recommended_next_areas=["Testing"],
                suggested_resources=[],
                deadline_status="none",
                days_remaining=None,
                created_at=now,
                updated_at=None,
            )
        ]
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
    app.dependency_overrides[get_learning_goal_service] = lambda: service
    app.dependency_overrides[get_db_read_session] = _session_override
    client = TestClient(app, raise_server_exceptions=False)

    try:
        response = client.get("/api/v1/learning-goals", headers={"Authorization": "Bearer access-token"})
    finally:
        client.close()

    assert response.status_code == 200
    assert response.json()[0]["id"] == str(goal_id)
    assert response.json()[0]["topic"] == "Python"
    assert response.json()[0]["recommended_next_areas"] == ["Testing"]
    assert response.json()[0]["deadline_status"] == "none"
    assert service.received_user_id == user.id


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
