from fastapi import APIRouter

from src.presentation.dependencies.auth import CurrentUser
from src.presentation.mappers.user_mapper import to_user_response
from src.presentation.schemas.user import UserResponse

router = APIRouter(prefix="/users", tags=["users"])



@router.get("/me", response_model=UserResponse)
async def get_me(current_user: CurrentUser) -> UserResponse:
    return to_user_response(current_user)
