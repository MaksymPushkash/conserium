from fastapi import Depends, Query

from src.auth.auth import CurrentUser
from src.postgres import AsyncReadSession, get_db_read_session
from src.routing import APIRouter
from src.stats.schemas import (
    DailyDigestResponse,
    StatsOverviewResponse,
    StatsTimelineResponse,
    WeeklyReportResponse,
)
from src.stats.service import stats

router = APIRouter(prefix="/stats", tags=["stats"])


@router.get("/overview", response_model=StatsOverviewResponse)
async def get_stats_overview(
    current_user: CurrentUser,
    session: AsyncReadSession = Depends(get_db_read_session),
) -> StatsOverviewResponse:
    return await stats.get_overview(session, current_user.id)


@router.get("/timeline", response_model=StatsTimelineResponse)
async def get_stats_timeline(
    current_user: CurrentUser,
    months: int = Query(default=6, ge=1, le=24),
    session: AsyncReadSession = Depends(get_db_read_session),
) -> StatsTimelineResponse:
    return await stats.get_timeline(session, current_user.id, months=months)


@router.get("/daily-digest", response_model=DailyDigestResponse)
async def get_daily_digest(
    current_user: CurrentUser,
    limit: int = Query(default=3, ge=1, le=10),
    session: AsyncReadSession = Depends(get_db_read_session),
) -> DailyDigestResponse:
    return await stats.get_daily_digest(session, current_user.id, limit=limit)


@router.get("/weekly-report", response_model=WeeklyReportResponse)
async def get_weekly_report(
    current_user: CurrentUser,
    session: AsyncReadSession = Depends(get_db_read_session),
) -> WeeklyReportResponse:
    return await stats.get_weekly_report(session, current_user.id)

__all__ = ["router"]
