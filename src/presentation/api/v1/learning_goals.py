from uuid import UUID

from dishka.integrations.fastapi import FromDishka, inject
from fastapi import APIRouter, Response, status

from src.application.use_cases.learning_goals import (
    CreateLearningGoalUseCase,
    DeleteLearningGoalUseCase,
    ListLearningGoalRemindersUseCase,
    ListLearningGoalsUseCase,
    RankLearningGoalResourcesUseCase,
    UpdateLearningGoalUseCase,
)
from src.presentation.dependencies.auth import CurrentUser
from src.presentation.mappers.learning_goal_mapper import (
    to_create_learning_goal_dto,
    to_learning_goal_response,
    to_ranked_resource_response,
    to_update_learning_goal_dto,
)
from src.presentation.schemas.learning_goal import (
    LearningGoalRequest,
    LearningGoalResponse,
    LearningGoalUpdateRequest,
    RankedLearningResourceResponse,
)

router = APIRouter(prefix="/learning-goals", tags=["learning-goals"])


@router.get("", response_model=list[LearningGoalResponse])
@inject
async def list_learning_goals(
    current_user: CurrentUser,
    use_case: FromDishka[ListLearningGoalsUseCase],
) -> list[LearningGoalResponse]:
    result = await use_case(user_id=current_user.id)
    return [to_learning_goal_response(goal) for goal in result]


@router.get("/reminders", response_model=list[LearningGoalResponse])
@inject
async def list_learning_goal_reminders(
    current_user: CurrentUser,
    use_case: FromDishka[ListLearningGoalRemindersUseCase],
) -> list[LearningGoalResponse]:
    result = await use_case(user_id=current_user.id)
    return [to_learning_goal_response(goal) for goal in result]


@router.get("/{goal_id}/resources", response_model=list[RankedLearningResourceResponse])
@inject
async def rank_learning_goal_resources(
    goal_id: UUID,
    current_user: CurrentUser,
    use_case: FromDishka[RankLearningGoalResourcesUseCase],
    refresh: bool = False,
) -> list[RankedLearningResourceResponse]:
    result = await use_case(user_id=current_user.id, goal_id=goal_id, refresh=refresh)
    return [to_ranked_resource_response(resource) for resource in result]


@router.post("", response_model=LearningGoalResponse, status_code=status.HTTP_201_CREATED)
@inject
async def create_learning_goal(
    body: LearningGoalRequest,
    current_user: CurrentUser,
    use_case: FromDishka[CreateLearningGoalUseCase],
) -> LearningGoalResponse:
    result = await use_case(to_create_learning_goal_dto(body, current_user.id))
    return to_learning_goal_response(result)


@router.patch("/{goal_id}", response_model=LearningGoalResponse)
@inject
async def update_learning_goal(
    goal_id: UUID,
    body: LearningGoalUpdateRequest,
    current_user: CurrentUser,
    use_case: FromDishka[UpdateLearningGoalUseCase],
) -> LearningGoalResponse:
    result = await use_case(to_update_learning_goal_dto(goal_id, body, current_user.id))
    return to_learning_goal_response(result)


@router.delete("/{goal_id}", status_code=status.HTTP_204_NO_CONTENT)
@inject
async def delete_learning_goal(
    goal_id: UUID,
    current_user: CurrentUser,
    use_case: FromDishka[DeleteLearningGoalUseCase],
) -> Response:
    await use_case(user_id=current_user.id, goal_id=goal_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
