from dishka.integrations.fastapi import FromDishka, inject
from fastapi import APIRouter, Response, status

from src.application.use_cases.auth.delete_account_use_case import DeleteAccountUseCase
from src.presentation.dependencies.auth import CurrentUser
from src.presentation.mappers.user_mapper import to_user_response
from src.presentation.schemas.user import UserResponse

router = APIRouter(prefix="/users", tags=["users"])



@router.get("/me", response_model=UserResponse)
async def get_me(current_user: CurrentUser) -> UserResponse:
    return to_user_response(current_user)


@router.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
@inject
async def delete_me(current_user: CurrentUser, use_case: FromDishka[DeleteAccountUseCase]) -> Response:
    await use_case(current_user.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
