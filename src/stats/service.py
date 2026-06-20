from uuid import UUID

from src.postgres import AsyncReadSession
from src.stats.repository import StatsRepository
from src.stats.schemas import (
    DailyDigestItemResponse,
    DailyDigestResponse,
    StatsOverviewResponse,
    StatsTimelineBucketResponse,
    StatsTimelineResponse,
    WeeklyReportResponse,
)


class StatsService:
    async def get_overview(self, session: AsyncReadSession, user_id: UUID) -> StatsOverviewResponse:
        overview = await StatsRepository.from_session(session).get_overview(user_id=user_id)
        return StatsOverviewResponse.model_validate(overview)

    async def get_timeline(self, session: AsyncReadSession, user_id: UUID, *, months: int) -> StatsTimelineResponse:
        buckets = await StatsRepository.from_session(session).get_learning_timeline(user_id=user_id, months=months)
        return StatsTimelineResponse(
            items=[StatsTimelineBucketResponse.model_validate(bucket) for bucket in buckets],
            months=months,
        )

    async def get_daily_digest(self, session: AsyncReadSession, user_id: UUID, *, limit: int) -> DailyDigestResponse:
        items = await StatsRepository.from_session(session).get_daily_digest_items(user_id=user_id, limit=limit)
        return DailyDigestResponse(items=[DailyDigestItemResponse.model_validate(item) for item in items])

    async def get_weekly_report(self, session: AsyncReadSession, user_id: UUID) -> WeeklyReportResponse:
        report = await StatsRepository.from_session(session).get_weekly_report(user_id=user_id)
        return WeeklyReportResponse(
            saved_documents=report.saved_documents,
            active_documents=report.active_documents,
            query_count=report.query_count,
            citation_count=report.citation_count,
            ready_documents=report.ready_documents,
            failed_documents=report.failed_documents,
            stale_documents=report.stale_documents,
            summary=_summary(report.saved_documents, report.active_documents, report.query_count),
            recommended_actions=_recommended_actions(
                stale_documents=report.stale_documents,
                failed_documents=report.failed_documents,
                query_count=report.query_count,
                saved_documents=report.saved_documents,
            ),
        )


def _summary(saved_documents: int, active_documents: int, query_count: int) -> str:
    if saved_documents == 0 and query_count == 0:
        return "No meaningful workspace activity in the last 7 days."
    return f"{saved_documents} sources saved, {active_documents} sources revisited, {query_count} queries asked in the last 7 days."


def _recommended_actions(
    *,
    stale_documents: int,
    failed_documents: int,
    query_count: int,
    saved_documents: int,
) -> list[str]:
    actions: list[str] = []
    if failed_documents:
        actions.append("Retry failed processing jobs.")
    if stale_documents:
        actions.append("Review stale documents with the daily digest.")
    if saved_documents and query_count == 0:
        actions.append("Ask a scoped question about recently saved sources.")
    if not actions:
        actions.append("Keep adding sources and use gaps to decide what to study next.")
    return actions


stats = StatsService()

__all__ = ["StatsService", "stats"]
