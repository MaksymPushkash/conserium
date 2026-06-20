from src.kit.cache.redis import dispose_redis


async def dispose_dependencies() -> None:
    await dispose_redis()
