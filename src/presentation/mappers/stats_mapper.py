from src.application.dtos.stats_dtos import DailyDigestDTO, StatsOverviewDTO, StatsTimelineDTO, WeeklyReportDTO
from src.presentation.schemas.stats import (
    DailyDigestItemResponse,
    DailyDigestResponse,
    StatsOverviewResponse,
    StatsTimelineBucketResponse,
    StatsTimelineResponse,
    WeeklyReportResponse,
)


def to_stats_overview_response(dto: StatsOverviewDTO) -> StatsOverviewResponse:
    return StatsOverviewResponse(
        total_documents=dto.total_documents,
        ready_documents=dto.ready_documents,
        processing_documents=dto.processing_documents,
        failed_documents=dto.failed_documents,
        hot_documents=dto.hot_documents,
        cold_documents=dto.cold_documents,
        forgotten_documents=dto.forgotten_documents,
        active_documents=dto.active_documents,
        query_count=dto.query_count,
        citation_count=dto.citation_count,
    )


def to_stats_timeline_response(dto: StatsTimelineDTO) -> StatsTimelineResponse:
    return StatsTimelineResponse(
        items=[
            StatsTimelineBucketResponse(
                month=item.month,
                saved_documents=item.saved_documents,
                active_documents=item.active_documents,
                query_count=item.query_count,
                citation_count=item.citation_count,
            )
            for item in dto.items
        ],
        months=dto.months,
    )


def to_daily_digest_response(dto: DailyDigestDTO) -> DailyDigestResponse:
    return DailyDigestResponse(
        items=[
            DailyDigestItemResponse(
                document_id=item.document_id,
                title=item.title,
                summary=item.summary,
                question=item.question,
                reason=item.reason,
                last_used_at=item.last_used_at,
                days_since_activity=item.days_since_activity,
            )
            for item in dto.items
        ]
    )


def to_weekly_report_response(dto: WeeklyReportDTO) -> WeeklyReportResponse:
    return WeeklyReportResponse(
        saved_documents=dto.saved_documents,
        active_documents=dto.active_documents,
        query_count=dto.query_count,
        citation_count=dto.citation_count,
        ready_documents=dto.ready_documents,
        failed_documents=dto.failed_documents,
        stale_documents=dto.stale_documents,
        summary=dto.summary,
        recommended_actions=dto.recommended_actions,
    )
