from uuid import UUID

from src.application.dtos.auth_dtos import TokenResponseDTO
from src.application.interfaces.cache import ICache
from src.application.interfaces.jwt_service import IJWTService


class BaseAuthUseCase:
    def __init__(self, jwt_service: IJWTService, cache: ICache, refresh_token_ttl_seconds: int) -> None:
        self._jwt_service = jwt_service
        self._cache = cache
        self._refresh_token_ttl_seconds = refresh_token_ttl_seconds

    async def _issue_tokens(self, user_id: UUID) -> TokenResponseDTO:
        access_token = self._jwt_service.generate_access_token(user_id)
        refresh_token = self._jwt_service.generate_refresh_token(user_id)
        await self._cache.set(
            key=f"refresh:{refresh_token}",
            value=str(user_id),
            ttl=self._refresh_token_ttl_seconds,
        )
        return TokenResponseDTO(access_token=access_token, refresh_token=refresh_token)