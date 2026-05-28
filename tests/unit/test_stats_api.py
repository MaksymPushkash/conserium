import uuid
from collections.abc import Mapping
from datetime import UTC, datetime
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from src.application.dtos.stats_dtos import (
    DailyDigestDTO,
    DailyDigestItemDTO,
    StatsOverviewDTO,
    StatsTimelineBucketDTO,
    StatsTimelineDTO,
    WeeklyReportDTO,
)
from src.application.ports.auth.jwt_service import IJWTService
from src.application.ports.persistence.unit_of_work import IUnitOfWork
from src.application.use_cases.stats import GetDailyDigestUseCase, GetStatsOverviewUseCase, GetWeeklyReportUseCase
from src.application.use_cases.stats.get_stats_timeline_use_case import GetStatsTimelineUseCase
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
    def __init__(self, result: StatsOverviewDTO) -> None:
        self._result = result
        self.received_user_id: uuid.UUID | None = None

    async def __call__(self, user_id: uuid.UUID) -> StatsOverviewDTO:
        self.received_user_id = user_id
        return self._result


class _ReturningTimelineUseCase:
    def __init__(self, result: StatsTimelineDTO) -> None:
        self._result = result
        self.received_user_id: uuid.UUID | None = None
        self.received_months: int | None = None

    async def __call__(self, user_id: uuid.UUID, *, months: int = 6) -> StatsTimelineDTO:
        self.received_user_id = user_id
        self.received_months = months
        return self._result


class _ReturningDailyDigestUseCase:
    def __init__(self, result: DailyDigestDTO) -> None:
        self._result = result
        self.received_user_id: uuid.UUID | None = None
        self.received_limit: int | None = None

    async def __call__(self, user_id: uuid.UUID, *, limit: int = 3) -> DailyDigestDTO:
        self.received_user_id = user_id
        self.received_limit = limit
        return self._result


class _ReturningWeeklyReportUseCase:
    def __init__(self, result: WeeklyReportDTO) -> None:
        self._result = result
        self.received_user_id: uuid.UUID | None = None

    async def __call__(self, user_id: uuid.UUID) -> WeeklyReportDTO:
        self.received_user_id = user_id
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


def test_stats_overview_route_returns_user_stats() -> None:
    user = _make_user()
    use_case = _ReturningUseCase(
        StatsOverviewDTO(
            total_documents=8,
            ready_documents=5,
            processing_documents=2,
            failed_documents=1,
            hot_documents=3,
            cold_documents=2,
            forgotten_documents=1,
            active_documents=6,
            query_count=11,
            citation_count=7,
        )
    )
    jwt_service = MagicMock()
    jwt_service.verify_access_token.return_value = user.id
    app = create_app()
    app.state.dishka_container = _FakeRootContainer(
        {
            IJWTService: jwt_service,
            IUnitOfWork: _FakeUnitOfWork(user),
            GetStatsOverviewUseCase: use_case,
        }
    )
    client = TestClient(app, raise_server_exceptions=False)

    try:
        response = client.get("/api/v1/stats/overview", headers={"Authorization": "Bearer access-token"})
    finally:
        client.close()

    assert response.status_code == 200
    assert response.json()["total_documents"] == 8
    assert response.json()["forgotten_documents"] == 1
    assert response.json()["query_count"] == 11
    assert use_case.received_user_id == user.id


def test_stats_timeline_route_returns_monthly_activity() -> None:
    user = _make_user()
    use_case = _ReturningTimelineUseCase(
        StatsTimelineDTO(
            items=[
                StatsTimelineBucketDTO(
                    month="2026-05",
                    saved_documents=3,
                    active_documents=2,
                    query_count=5,
                    citation_count=4,
                )
            ],
            months=6,
        )
    )
    jwt_service = MagicMock()
    jwt_service.verify_access_token.return_value = user.id
    app = create_app()
    app.state.dishka_container = _FakeRootContainer(
        {
            IJWTService: jwt_service,
            IUnitOfWork: _FakeUnitOfWork(user),
            GetStatsTimelineUseCase: use_case,
        }
    )
    client = TestClient(app, raise_server_exceptions=False)

    try:
        response = client.get("/api/v1/stats/timeline?months=6", headers={"Authorization": "Bearer access-token"})
    finally:
        client.close()

    assert response.status_code == 200
    assert response.json()["items"][0]["month"] == "2026-05"
    assert response.json()["items"][0]["query_count"] == 5
    assert response.json()["months"] == 6
    assert use_case.received_user_id == user.id
    assert use_case.received_months == 6


def test_daily_digest_route_returns_stale_document_questions() -> None:
    user = _make_user()
    document_id = uuid.uuid4()
    last_used_at = datetime(2026, 5, 1, tzinfo=UTC)
    use_case = _ReturningDailyDigestUseCase(
        DailyDigestDTO(
            items=[
                DailyDigestItemDTO(
                    document_id=document_id,
                    title="Clean Architecture",
                    summary="Architecture notes",
                    question="How do boundaries work?",
                    reason="No activity for 12 days.",
                    last_used_at=last_used_at,
                    days_since_activity=12,
                )
            ]
        )
    )
    jwt_service = MagicMock()
    jwt_service.verify_access_token.return_value = user.id
    app = create_app()
    app.state.dishka_container = _FakeRootContainer(
        {
            IJWTService: jwt_service,
            IUnitOfWork: _FakeUnitOfWork(user),
            GetDailyDigestUseCase: use_case,
        }
    )
    client = TestClient(app, raise_server_exceptions=False)

    try:
        response = client.get("/api/v1/stats/daily-digest?limit=2", headers={"Authorization": "Bearer access-token"})
    finally:
        client.close()

    assert response.status_code == 200
    assert response.json()["items"][0]["document_id"] == str(document_id)
    assert response.json()["items"][0]["question"] == "How do boundaries work?"
    assert use_case.received_user_id == user.id
    assert use_case.received_limit == 2


def test_weekly_report_route_returns_actionable_summary() -> None:
    user = _make_user()
    use_case = _ReturningWeeklyReportUseCase(
        WeeklyReportDTO(
            saved_documents=4,
            active_documents=3,
            query_count=2,
            citation_count=5,
            ready_documents=9,
            failed_documents=1,
            stale_documents=6,
            summary="4 sources saved, 3 sources revisited, 2 queries asked in the last 7 days.",
            recommended_actions=["Retry failed processing jobs."],
        )
    )
    jwt_service = MagicMock()
    jwt_service.verify_access_token.return_value = user.id
    app = create_app()
    app.state.dishka_container = _FakeRootContainer(
        {
            IJWTService: jwt_service,
            IUnitOfWork: _FakeUnitOfWork(user),
            GetWeeklyReportUseCase: use_case,
        }
    )
    client = TestClient(app, raise_server_exceptions=False)

    try:
        response = client.get("/api/v1/stats/weekly-report", headers={"Authorization": "Bearer access-token"})
    finally:
        client.close()

    assert response.status_code == 200
    assert response.json()["stale_documents"] == 6
    assert response.json()["recommended_actions"] == ["Retry failed processing jobs."]
    assert use_case.received_user_id == user.id
