from uuid import UUID

from src.application.dtos.auth_dtos import TokenResponseDTO
from src.application.interfaces.cache import ICache
from src.application.interfaces.jwt_service import IJWTService
from src.core.config import settings


class BaseAuthUseCase:
    def __init__(self, jwt_service: IJWTService, cache: ICache) -> None:
        self._jwt_service = jwt_service
        self._cache = cache

    async def _issue_tokens(self, user_id: UUID) -> TokenResponseDTO:
        access_token = self._jwt_service.generate_access_token(user_id)
        refresh_token = self._jwt_service.generate_refresh_token(user_id)
        await self._cache.set(
            key=f"refresh:{refresh_token}",
            value=str(user_id),
            ttl=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS * 24 * 3600,
        )
        return TokenResponseDTO(access_token=access_token, refresh_token=refresh_token)