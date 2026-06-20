from uuid import UUID

from fastapi import Depends, Response, status

from src.auth.auth import CurrentUser
from src.integrations.clients import WebResourceFetcherProtocol
from src.learning_goals.schemas import (
    LearningGoalRequest,
    LearningGoalResponse,
    LearningGoalUpdateRequest,
    RankedLearningResourceResponse,
)
from src.learning_goals.service import LearningGoalService, get_learning_goal_service, get_web_resource_fetcher
from src.postgres import AsyncReadSession, AsyncSession, get_db_read_session, get_db_session
from src.routing import APIRouter

router = APIRouter(prefix="/learning-goals", tags=["learning-goals"])


@router.get("", response_model=list[LearningGoalResponse])
async def list_learning_goals(
    current_user: CurrentUser,
    session: AsyncReadSession = Depends(get_db_read_session),
    service: LearningGoalService = Depends(get_learning_goal_service),
) -> list[LearningGoalResponse]:
    return await service.list_goals(session, user_id=current_user.id)


@router.get("/reminders", response_model=list[LearningGoalResponse])
async def list_learning_goal_reminders(
    current_user: CurrentUser,
    session: AsyncReadSession = Depends(get_db_read_session),
    service: LearningGoalService = Depends(get_learning_goal_service),
) -> list[LearningGoalResponse]:
    return await service.reminders(session, user_id=current_user.id)


@router.get("/{goal_id}/resources", response_model=list[RankedLearningResourceResponse])
async def rank_learning_goal_resources(
    goal_id: UUID,
    current_user: CurrentUser,
    refresh: bool = False,
    session: AsyncSession = Depends(get_db_session),
    service: LearningGoalService = Depends(get_learning_goal_service),
    web_resource_fetcher: WebResourceFetcherProtocol = Depends(get_web_resource_fetcher),
) -> list[RankedLearningResourceResponse]:
    return await service.rank_resources(
        session,
        user_id=current_user.id,
        goal_id=goal_id,
        refresh=refresh,
        web_resource_fetcher=web_resource_fetcher,
    )


@router.post("", response_model=LearningGoalResponse, status_code=status.HTTP_201_CREATED)
async def create_learning_goal(
    body: LearningGoalRequest,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_db_session),
    service: LearningGoalService = Depends(get_learning_goal_service),
) -> LearningGoalResponse:
    return await service.create(session, user_id=current_user.id, body=body)


@router.patch("/{goal_id}", response_model=LearningGoalResponse)
async def update_learning_goal(
    goal_id: UUID,
    body: LearningGoalUpdateRequest,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_db_session),
    service: LearningGoalService = Depends(get_learning_goal_service),
) -> LearningGoalResponse:
    return await service.update(session, user_id=current_user.id, goal_id=goal_id, body=body)


@router.delete("/{goal_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_learning_goal(
    goal_id: UUID,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_db_session),
    service: LearningGoalService = Depends(get_learning_goal_service),
) -> Response:
    await service.delete(session, user_id=current_user.id, goal_id=goal_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


__all__ = ["router"]
