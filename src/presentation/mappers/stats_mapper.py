from src.application.dtos.stats_dtos import StatsOverviewDTO, StatsTimelineDTO
from src.presentation.schemas.stats import StatsOverviewResponse, StatsTimelineBucketResponse, StatsTimelineResponse


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
