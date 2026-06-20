from fastapi import Depends

from src.auth.auth import CurrentUser
from src.observability.schemas import ObservabilitySummaryResponse
from src.observability.service import ObservabilityService, get_observability_service
from src.postgres import AsyncReadSession, get_db_read_session
from src.routing import APIRouter

router = APIRouter(prefix="/observability", tags=["observability"])


@router.get("/summary", response_model=ObservabilitySummaryResponse)
async def observability_summary(
    current_user: CurrentUser,
    session: AsyncReadSession = Depends(get_db_read_session),
    service: ObservabilityService = Depends(get_observability_service),
) -> ObservabilitySummaryResponse:
    return await service.summary(session, user_id=current_user.id)


__all__ = ["router"]
