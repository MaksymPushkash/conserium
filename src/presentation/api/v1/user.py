from dishka.integrations.fastapi import FromDishka, inject
from fastapi import APIRouter, Response, status

from src.application.use_cases.auth.delete_account_use_case import DeleteAccountUseCase
from src.application.use_cases.auth.update_user_preferences_use_case import (
    UpdateUserPreferencesDTO,
    UpdateUserPreferencesUseCase,
)
from src.presentation.dependencies.auth import CurrentUser
from src.presentation.mappers.user_mapper import to_user_preferences_response, to_user_response
from src.presentation.schemas.user import UserPreferencesResponse, UserPreferencesUpdateRequest, UserResponse

router = APIRouter(prefix="/users", tags=["users"])



@router.get("/me", response_model=UserResponse)
async def get_me(current_user: CurrentUser) -> UserResponse:
    return to_user_response(current_user)


@router.get("/preferences", response_model=UserPreferencesResponse)
async def get_preferences(current_user: CurrentUser) -> UserPreferencesResponse:
    return to_user_preferences_response(current_user.preferences)


@router.patch("/preferences", response_model=UserPreferencesResponse)
@inject
async def update_preferences(
    body: UserPreferencesUpdateRequest,
    current_user: CurrentUser,
    use_case: FromDishka[UpdateUserPreferencesUseCase],
) -> UserPreferencesResponse:
    user = await use_case(UpdateUserPreferencesDTO(user_id=current_user.id, preferences=body.model_dump()))
    return to_user_preferences_response(user.preferences)


@router.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
@inject
async def delete_me(current_user: CurrentUser, use_case: FromDishka[DeleteAccountUseCase]) -> Response:
    await use_case(current_user.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
