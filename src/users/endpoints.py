from fastapi import Depends, Response, status

from src.auth.auth import CurrentUser
from src.postgres import AsyncSession, get_db_session
from src.routing import APIRouter
from src.users.schemas import UserPreferencesResponse, UserPreferencesUpdateRequest, UserResponse
from src.users.service import users

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: CurrentUser) -> UserResponse:
    return users.response(current_user)


@router.get("/preferences", response_model=UserPreferencesResponse)
async def get_preferences(current_user: CurrentUser) -> UserPreferencesResponse:
    return users.preferences_response(current_user.preferences)


@router.patch("/preferences", response_model=UserPreferencesResponse)
async def update_preferences(
    body: UserPreferencesUpdateRequest,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_db_session),
) -> UserPreferencesResponse:
    return await users.update_preferences(session, user_id=current_user.id, preferences=body.model_dump())


@router.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
async def delete_me(current_user: CurrentUser, session: AsyncSession = Depends(get_db_session)) -> Response:
    await users.delete(session, user_id=current_user.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)

__all__ = ["router"]
