from src.application.dtos.auth_dtos import RefreshDTO
from src.application.ports.cache.cache import ICache


class LogoutUseCase:
    def __init__(self, cache: ICache) -> None:
        self._cache = cache

    async def __call__(self, dto: RefreshDTO) -> None:
        await self._cache.delete(f"refresh:{dto.refresh_token}")


class LogoutEverywhereUseCase:
    def __init__(self, cache: ICache) -> None:
        self._cache = cache

    async def __call__(self, user_id: object) -> int:
        return await self._cache.delete_by_value_prefix("refresh:", str(user_id))
