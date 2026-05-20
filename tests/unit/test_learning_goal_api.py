import uuid
from collections.abc import Mapping
from datetime import UTC, datetime
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from src.application.dtos.learning_goal_dtos import LearningGoalDTO
from src.application.ports.auth.jwt_service import IJWTService
from src.application.ports.persistence.unit_of_work import IUnitOfWork
from src.application.use_cases.learning_goals import ListLearningGoalsUseCase
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


class _ReturningLearningGoalsUseCase:
    def __init__(self, result: list[LearningGoalDTO]) -> None:
        self._result = result
        self.received_user_id: uuid.UUID | None = None

    async def __call__(self, *, user_id: uuid.UUID) -> list[LearningGoalDTO]:
        self.received_user_id = user_id
        return self._result


def test_list_learning_goals_route_serializes_response() -> None:
    user = _make_user()
    goal_id = uuid.uuid4()
    now = datetime.now(UTC)
    use_case = _ReturningLearningGoalsUseCase(
        [
            LearningGoalDTO(
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
    app.state.dishka_container = _FakeRootContainer(
        {
            IJWTService: jwt_service,
            IUnitOfWork: _FakeUnitOfWork(user),
            ListLearningGoalsUseCase: use_case,
        }
    )
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
