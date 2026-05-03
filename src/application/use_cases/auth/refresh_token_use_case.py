import uuid

from src.application.dtos.auth_dtos import RefreshDTO, TokenResponseDTO
from src.application.ports.auth.jwt_service import IJWTService
from src.application.ports.cache.cache import ICache
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
        token_user_id = self._jwt_service.verify_refresh_token(dto.refresh_token)
        key = f"refresh:{dto.refresh_token}"

        cached_user_id = await self._cache.get_del(key)
        if cached_user_id is None:
            raise InvalidTokenException("refresh token not found or expired")

        try:
            cache_user_id = uuid.UUID(cached_user_id)
        except ValueError as e:
            raise InvalidTokenException("refresh token session is corrupted") from e

        if cache_user_id != token_user_id:
            raise InvalidTokenException("refresh token session does not match token subject")

        return await self._issue_tokens(token_user_id)
