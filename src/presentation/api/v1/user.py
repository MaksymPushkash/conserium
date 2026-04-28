from fastapi import APIRouter

from src.presentation.dependencies.auth import CurrentUser
from src.presentation.schemas.user import UserResponse

router = APIRouter(prefix="/users", tags=["users"])



@router.get("/me", response_model=UserResponse)
async def get_me(current_user: CurrentUser) -> UserResponse:
    return UserResponse.from_entity(current_user)
