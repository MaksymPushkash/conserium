from dishka.integrations.fastapi import FromDishka, inject
from fastapi import APIRouter, Query

from src.application.use_cases.stats import GetStatsOverviewUseCase, GetStatsTimelineUseCase
from src.presentation.dependencies.auth import CurrentUser
from src.presentation.mappers.stats_mapper import to_stats_overview_response, to_stats_timeline_response
from src.presentation.schemas.stats import StatsOverviewResponse, StatsTimelineResponse

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
