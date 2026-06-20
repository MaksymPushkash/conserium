import uuid
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from src.postgres import AsyncReadSession
from src.stats.repository import (
    DailyDigestItemRecord,
    StatsOverviewRecord,
    StatsRepository,
    StatsTimelineBucket,
    WeeklyReportRecord,
)
from src.stats.service import StatsService

if TYPE_CHECKING:
    from pytest import MonkeyPatch


async def test_stats_overview_counts_documents_and_activity(monkeypatch: "MonkeyPatch") -> None:
    _set_stats_repository(monkeypatch)

    result = await StatsService().get_overview(_FakeSession(), uuid.uuid4())

    assert result.total_documents == 8
    assert result.ready_documents == 5
    assert result.processing_documents == 2
    assert result.failed_documents == 1
    assert result.hot_documents == 3
    assert result.cold_documents == 2
    assert result.forgotten_documents == 1
    assert result.active_documents == 6
    assert result.query_count == 11
    assert result.citation_count == 7


class _FakeStatsRepository:
    async def get_overview(self, *, user_id: uuid.UUID) -> StatsOverviewRecord:
        return StatsOverviewRecord(
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

    async def get_learning_timeline(self, *, user_id: uuid.UUID, months: int) -> list[StatsTimelineBucket]:
        return [
            StatsTimelineBucket(
                month="2026-04",
                saved_documents=2,
                active_documents=1,
                query_count=4,
                citation_count=3,
            ),
            StatsTimelineBucket(
                month="2026-05",
                saved_documents=3,
                active_documents=2,
                query_count=5,
                citation_count=4,
            ),
        ]

    async def get_daily_digest_items(self, *, user_id: uuid.UUID, limit: int = 3) -> list[DailyDigestItemRecord]:
        return [
            DailyDigestItemRecord(
                document_id=uuid.uuid4(),
                title="Clean Architecture",
                summary="Architecture notes",
                question="How do boundaries work?",
                reason="No activity for 12 days.",
                last_used_at=datetime.now(UTC) - timedelta(days=12),
                days_since_activity=12,
            )
        ][:limit]

    async def get_weekly_report(self, *, user_id: uuid.UUID) -> WeeklyReportRecord:
        return WeeklyReportRecord(
            saved_documents=4,
            active_documents=3,
            query_count=2,
            citation_count=5,
            ready_documents=9,
            failed_documents=1,
            stale_documents=6,
        )


async def test_stats_timeline_returns_monthly_buckets(monkeypatch: "MonkeyPatch") -> None:
    _set_stats_repository(monkeypatch)

    result = await StatsService().get_timeline(_FakeSession(), uuid.uuid4(), months=2)

    assert result.months == 2
    assert [item.month for item in result.items] == ["2026-04", "2026-05"]
    assert result.items[0].saved_documents == 2
    assert result.items[1].query_count == 5


async def test_daily_digest_returns_stale_document_questions(monkeypatch: "MonkeyPatch") -> None:
    _set_stats_repository(monkeypatch)

    result = await StatsService().get_daily_digest(_FakeSession(), uuid.uuid4(), limit=3)

    assert result.items[0].title == "Clean Architecture"
    assert result.items[0].question == "How do boundaries work?"
    assert result.items[0].days_since_activity == 12


async def test_weekly_report_adds_recommended_actions(monkeypatch: "MonkeyPatch") -> None:
    _set_stats_repository(monkeypatch)

    result = await StatsService().get_weekly_report(_FakeSession(), uuid.uuid4())

    assert result.saved_documents == 4
    assert result.summary == "4 sources saved, 3 sources revisited, 2 queries asked in the last 7 days."
    assert "Retry failed processing jobs." in result.recommended_actions


class _FakeSession(AsyncReadSession):
    pass


def _set_stats_repository(monkeypatch: "MonkeyPatch") -> None:
    monkeypatch.setattr(StatsRepository, "from_session", classmethod(lambda cls, session: _FakeStatsRepository()))
