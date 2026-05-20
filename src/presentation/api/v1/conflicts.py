from uuid import UUID

from dishka.integrations.fastapi import FromDishka, inject
from fastapi import APIRouter, Query

from src.application.dtos.conflict_dtos import ConflictDetectionDTO
from src.application.use_cases.conflicts import DetectConflictsUseCase
from src.presentation.dependencies.auth import CurrentUser
from src.presentation.mappers.conflict_mapper import to_conflict_detection_response
from src.presentation.schemas.conflict import ConflictDetectionResponse

router = APIRouter(prefix="/conflicts", tags=["conflicts"])


@router.get("", response_model=ConflictDetectionResponse)
@inject
async def detect_conflicts(
    current_user: CurrentUser,
    use_case: FromDishka[DetectConflictsUseCase],
    collection_id: UUID | None = Query(default=None),
    limit: int = Query(default=100, ge=2, le=200),
) -> ConflictDetectionResponse:
    result = await use_case(
        ConflictDetectionDTO(
            user_id=current_user.id,
            collection_id=collection_id,
            limit=limit,
        )
    )
    return to_conflict_detection_response(result)
