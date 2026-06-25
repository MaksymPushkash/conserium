import uuid
from collections.abc import Mapping
from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from src.auth.jwt_service import JWTService
from src.main import create_app
from src.models.user import UserModel
from src.stats.schemas import (
    DailyDigestItemResponse,
    DailyDigestResponse,
    StatsOverviewResponse,
    StatsTimelineBucketResponse,
    StatsTimelineResponse,
    WeeklyReportResponse,
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


class _ReturningStatsService:
    def __init__(self, result: StatsOverviewResponse) -> None:
        self._result = result
        self.received_user_id: uuid.UUID | None = None

    async def get_overview(self, session: object, user_id: uuid.UUID) -> StatsOverviewResponse:
        self.received_user_id = user_id
        return self._result


class _ReturningTimelineStatsService:
    def __init__(self, result: StatsTimelineResponse) -> None:
        self._result = result
        self.received_user_id: uuid.UUID | None = None
        self.received_months: int | None = None

    async def get_timeline(self, session: object, user_id: uuid.UUID, *, months: int) -> StatsTimelineResponse:
        self.received_user_id = user_id
        self.received_months = months
        return self._result


class _ReturningDailyDigestStatsService:
    def __init__(self, result: DailyDigestResponse) -> None:
        self._result = result
        self.received_user_id: uuid.UUID | None = None
        self.received_limit: int | None = None

    async def get_daily_digest(self, session: object, user_id: uuid.UUID, *, limit: int) -> DailyDigestResponse:
        self.received_user_id = user_id
        self.received_limit = limit
        return self._result


class _ReturningWeeklyReportStatsService:
    def __init__(self, result: WeeklyReportResponse) -> None:
        self._result = result
        self.received_user_id: uuid.UUID | None = None

    async def get_weekly_report(self, session: object, user_id: uuid.UUID) -> WeeklyReportResponse:
        self.received_user_id = user_id
        return self._result


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


async def _fake_read_session() -> object:
    yield object()


def _set_stats_service(monkeypatch: pytest.MonkeyPatch, service: object) -> None:
    import src.stats.endpoints as stats_endpoints

    monkeypatch.setattr(stats_endpoints, "stats", service)
    stats_endpoints.router.dependency_overrides_provider = None


def test_stats_overview_route_returns_user_stats(monkeypatch: pytest.MonkeyPatch) -> None:
    user = _make_user()
    service = _ReturningStatsService(
        StatsOverviewResponse(
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
    _set_stats_service(monkeypatch, service)
    jwt_service = MagicMock()
    jwt_service.verify_access_token.return_value = user.id
    app = create_app()
    from src.postgres import get_db_read_session

    app.dependency_overrides[get_db_read_session] = _fake_read_session
    apply_dependency_overrides(app, _FakeDependencyContainer(
        {
            JWTService: jwt_service,
            UserRepository: _FakeRepositorySession(user),
        }
    )._dependencies)
    client = TestClient(app, raise_server_exceptions=False)

    try:
        response = client.get("/api/v1/stats/overview", headers={"Authorization": "Bearer access-token"})
    finally:
        client.close()

    assert response.status_code == 200
    assert response.json()["total_documents"] == 8
    assert response.json()["forgotten_documents"] == 1
    assert response.json()["query_count"] == 11
    assert service.received_user_id == user.id


def test_stats_timeline_route_returns_monthly_activity(monkeypatch: pytest.MonkeyPatch) -> None:
    user = _make_user()
    service = _ReturningTimelineStatsService(
        StatsTimelineResponse(
            items=[
                StatsTimelineBucketResponse(
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
    _set_stats_service(monkeypatch, service)
    jwt_service = MagicMock()
    jwt_service.verify_access_token.return_value = user.id
    app = create_app()
    from src.postgres import get_db_read_session

    app.dependency_overrides[get_db_read_session] = _fake_read_session
    apply_dependency_overrides(app, _FakeDependencyContainer(
        {
            JWTService: jwt_service,
            UserRepository: _FakeRepositorySession(user),
        }
    )._dependencies)
    client = TestClient(app, raise_server_exceptions=False)

    try:
        response = client.get("/api/v1/stats/timeline?months=6", headers={"Authorization": "Bearer access-token"})
    finally:
        client.close()

    assert response.status_code == 200
    assert response.json()["items"][0]["month"] == "2026-05"
    assert response.json()["items"][0]["query_count"] == 5
    assert response.json()["months"] == 6
    assert service.received_user_id == user.id
    assert service.received_months == 6


def test_daily_digest_route_returns_stale_document_questions(monkeypatch: pytest.MonkeyPatch) -> None:
    user = _make_user()
    document_id = uuid.uuid4()
    last_used_at = datetime(2026, 5, 1, tzinfo=UTC)
    service = _ReturningDailyDigestStatsService(
        DailyDigestResponse(
            items=[
                DailyDigestItemResponse(
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
    _set_stats_service(monkeypatch, service)
    jwt_service = MagicMock()
    jwt_service.verify_access_token.return_value = user.id
    app = create_app()
    from src.postgres import get_db_read_session

    app.dependency_overrides[get_db_read_session] = _fake_read_session
    apply_dependency_overrides(app, _FakeDependencyContainer(
        {
            JWTService: jwt_service,
            UserRepository: _FakeRepositorySession(user),
        }
    )._dependencies)
    client = TestClient(app, raise_server_exceptions=False)

    try:
        response = client.get("/api/v1/stats/daily-digest?limit=2", headers={"Authorization": "Bearer access-token"})
    finally:
        client.close()

    assert response.status_code == 200
    assert response.json()["items"][0]["document_id"] == str(document_id)
    assert response.json()["items"][0]["question"] == "How do boundaries work?"
    assert service.received_user_id == user.id
    assert service.received_limit == 2


def test_weekly_report_route_returns_actionable_summary(monkeypatch: pytest.MonkeyPatch) -> None:
    user = _make_user()
    service = _ReturningWeeklyReportStatsService(
        WeeklyReportResponse(
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
    _set_stats_service(monkeypatch, service)
    jwt_service = MagicMock()
    jwt_service.verify_access_token.return_value = user.id
    app = create_app()
    from src.postgres import get_db_read_session

    app.dependency_overrides[get_db_read_session] = _fake_read_session
    apply_dependency_overrides(app, _FakeDependencyContainer(
        {
            JWTService: jwt_service,
            UserRepository: _FakeRepositorySession(user),
        }
    )._dependencies)
    client = TestClient(app, raise_server_exceptions=False)

    try:
        response = client.get("/api/v1/stats/weekly-report", headers={"Authorization": "Bearer access-token"})
    finally:
        client.close()

    assert response.status_code == 200
    assert response.json()["stale_documents"] == 6
    assert response.json()["recommended_actions"] == ["Retry failed processing jobs."]
    assert service.received_user_id == user.id
