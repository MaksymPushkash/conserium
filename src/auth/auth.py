from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from src.auth.jwt_service import JWTServiceProtocol
from src.auth.service import get_jwt_service, get_user_repository
from src.kit.exceptions import InvalidTokenException, UserInactiveException
from src.models.user import UserModel
from src.users.repository import UserRepository

security = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    jwt_service: JWTServiceProtocol = Depends(get_jwt_service),
    user_repo: UserRepository = Depends(get_user_repository),
) -> UserModel:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        user_id = jwt_service.verify_access_token(credentials.credentials)
    except InvalidTokenException as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    user = await user_repo.get_by_id(user_id)

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="user not found",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        user.ensure_active()
    except UserInactiveException as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc

    return user


CurrentUser = Annotated[UserModel, Depends(get_current_user)]

__all__ = ["CurrentUser", "get_current_user"]
