from uuid import UUID

from fastapi import Depends, Query

from src.auth.auth import CurrentUser
from src.conflicts.dependencies import get_conflict_llm_service, get_conflict_service
from src.conflicts.schemas import ConflictDetectionResponse
from src.conflicts.service import ConflictService
from src.kit.ai.llm_service import LLMService
from src.postgres import AsyncSession, get_db_session
from src.routing import APIRouter

router = APIRouter(prefix="/conflicts", tags=["conflicts"])


@router.get("", response_model=ConflictDetectionResponse)
async def detect_conflicts(
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_db_session),
    service: ConflictService = Depends(get_conflict_service),
    llm_service: LLMService = Depends(get_conflict_llm_service),
    collection_id: UUID | None = Query(default=None),
    limit: int = Query(default=100, ge=2, le=200),
) -> ConflictDetectionResponse:
    return await service.detect(
        session,
        user_id=current_user.id,
        collection_id=collection_id,
        limit=limit,
        llm_service=llm_service,
    )


__all__ = ["router"]
