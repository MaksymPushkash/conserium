from collections.abc import AsyncIterator

from dishka import Provider, Scope, provide
from redis.asyncio import Redis

from src.application.ports.cache.cache import ICache
from src.application.ports.cache.document_status_cache import IDocumentStatusCache
from src.application.ports.conversations.conversation_store import IConversationStore
from src.core.config import settings
from src.infrastructure.cache.document_status_cache import RedisDocumentStatusCache
from src.infrastructure.cache.redis_cache import RedisCache
from src.infrastructure.cache.redis_conversation_store import RedisConversationStore


class CacheProvider(Provider):
    @provide(scope=Scope.APP)
    async def get_redis(self) -> AsyncIterator[Redis]:
        redis = Redis.from_url(settings.REDIS_URL, decode_responses=False)
        yield redis
        await redis.aclose()

    @provide(scope=Scope.APP)
    def get_cache(self, redis: Redis) -> ICache:
        return RedisCache(redis)

    @provide(scope=Scope.APP)
    def get_document_status_cache(self, redis: Redis) -> IDocumentStatusCache:
        return RedisDocumentStatusCache(redis)

    @provide(scope=Scope.APP)
    def get_conversation_store(self, cache: ICache) -> IConversationStore:
        return RedisConversationStore(cache)
