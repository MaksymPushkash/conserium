from dishka.integrations.fastapi import FromDishka, inject
from fastapi import APIRouter, Query

from src.application.use_cases.stats import (
    GetDailyDigestUseCase,
    GetStatsOverviewUseCase,
    GetStatsTimelineUseCase,
    GetWeeklyReportUseCase,
)
from src.presentation.dependencies.auth import CurrentUser
from src.presentation.mappers.stats_mapper import (
    to_daily_digest_response,
    to_stats_overview_response,
    to_stats_timeline_response,
    to_weekly_report_response,
)
from src.presentation.schemas.stats import (
    DailyDigestResponse,
    StatsOverviewResponse,
    StatsTimelineResponse,
    WeeklyReportResponse,
)

router = APIRouter(prefix="/stats", tags=["stats"])


@router.get("/overview", response_model=StatsOverviewResponse)
@inject
async def get_stats_overview(
    current_user: CurrentUser,
    use_case: FromDishka[GetStatsOverviewUseCase],
) -> StatsOverviewResponse:
    result = await use_case(current_user.id)
    return to_stats_overview_response(result)


@router.get("/timeline", response_model=StatsTimelineResponse)
@inject
async def get_stats_timeline(
    current_user: CurrentUser,
    use_case: FromDishka[GetStatsTimelineUseCase],
    months: int = Query(default=6, ge=1, le=24),
) -> StatsTimelineResponse:
    result = await use_case(current_user.id, months=months)
    return to_stats_timeline_response(result)


@router.get("/daily-digest", response_model=DailyDigestResponse)
@inject
async def get_daily_digest(
    current_user: CurrentUser,
    use_case: FromDishka[GetDailyDigestUseCase],
    limit: int = Query(default=3, ge=1, le=10),
) -> DailyDigestResponse:
    result = await use_case(current_user.id, limit=limit)
    return to_daily_digest_response(result)


@router.get("/weekly-report", response_model=WeeklyReportResponse)
@inject
async def get_weekly_report(
    current_user: CurrentUser,
    use_case: FromDishka[GetWeeklyReportUseCase],
) -> WeeklyReportResponse:
    result = await use_case(current_user.id)
    return to_weekly_report_response(result)
