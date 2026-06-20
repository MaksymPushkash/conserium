from functools import lru_cache

from redis.asyncio import Redis

from src.settings import settings


@lru_cache(maxsize=1)
def get_redis() -> Redis:
    return Redis.from_url(settings.REDIS_URL, decode_responses=False)


async def dispose_redis() -> None:
    if get_redis.cache_info().currsize:
        await get_redis().aclose()
        get_redis.cache_clear()
