from typing import Annotated

from dishka.integrations.fastapi import FromDishka, inject
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from src.application.ports.auth.jwt_service import IJWTService
from src.application.ports.persistence.unit_of_work import IUnitOfWork
from src.domain.entities.user_entity import UserEntity
from src.domain.exceptions import InvalidTokenException, UserInactiveException

security = HTTPBearer()


@inject
async def get_current_user(
    jwt_service: FromDishka[IJWTService],
    uow: FromDishka[IUnitOfWork],
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> UserEntity:
    try:
        user_id = jwt_service.verify_access_token(credentials.credentials)
    except InvalidTokenException as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
            headers={"WWW-Authenticate": "Bearer"},
        ) from e

    async with uow:
        user = await uow.user_repo.get_by_id(user_id)

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="user not found",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        user.ensure_active()
    except UserInactiveException as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e),
        ) from e

    return user


CurrentUser = Annotated[UserEntity, Depends(get_current_user)]
