import uuid

from src.application.dtos.auth_dtos import RefreshDTO, TokenResponseDTO
from src.application.interfaces.cache import ICache
from src.application.interfaces.jwt_service import IJWTService
from src.application.use_cases.auth.base import BaseAuthUseCase
from src.domain.exceptions import InvalidTokenException


class RefreshTokenUseCase(BaseAuthUseCase):
    def __init__(
        self,
        jwt_service: IJWTService,
        cache: ICache,
        refresh_token_ttl_seconds: int,
    ) -> None:
        super().__init__(jwt_service, cache, refresh_token_ttl_seconds)
 
    async def __call__(self, dto: RefreshDTO) -> TokenResponseDTO:
        key = f"refresh:{dto.refresh_token}"
 
        user_id_str = await self._cache.get(key)
        if user_id_str is None:
            raise InvalidTokenException("refresh token not found or expired")
 
        await self._cache.delete(key)
 
        user_id = uuid.UUID(user_id_str)
        return await self._issue_tokens(user_id)