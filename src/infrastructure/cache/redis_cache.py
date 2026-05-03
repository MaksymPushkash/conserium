from redis.asyncio import Redis

from src.application.ports.cache.cache import ICache


class RedisCache(ICache):
    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    async def get(self, key: str) -> str | None:
        value = await self._redis.get(key)
        return value.decode() if value else None

    async def get_del(self, key: str) -> str | None:
        value = await self._redis.getdel(key)
        return value.decode() if value else None

    async def set(self, key: str, value: str, ttl: int) -> None:
        await self._redis.setex(key, ttl, value)

    async def set_if_absent(self, key: str, value: str, ttl: int) -> bool:
        return bool(await self._redis.set(key, value, ex=ttl, nx=True))

    async def delete(self, key: str) -> None:
        await self._redis.delete(key)

    async def exists(self, key: str) -> bool:
        count = await self._redis.exists(key)
        return int(count) > 0
