from __future__ import annotations

from typing import Literal, overload

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from src.core.config import settings

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None
_redis_text: Redis | None = None
_redis_bytes: Redis | None = None


def get_worker_session_factory() -> async_sessionmaker[AsyncSession]:
    global _engine, _session_factory
    if _session_factory is None:
        _engine = create_async_engine(
            settings.DATABASE_URL,
            echo=settings.DEBUG,
            pool_size=settings.DATABASE_POOL_SIZE,
            max_overflow=settings.DATABASE_MAX_OVERFLOW,
            pool_pre_ping=True,
            pool_recycle=300,
        )
        _session_factory = async_sessionmaker(bind=_engine, expire_on_commit=False)
    return _session_factory


@overload
def get_worker_redis(*, decode_responses: Literal[True]) -> Redis: ...


@overload
def get_worker_redis(*, decode_responses: Literal[False]) -> Redis: ...


def get_worker_redis(*, decode_responses: bool) -> Redis:
    global _redis_text, _redis_bytes
    if decode_responses:
        if _redis_text is None:
            _redis_text = Redis.from_url(settings.REDIS_URL, decode_responses=True)
        return _redis_text
    if _redis_bytes is None:
        _redis_bytes = Redis.from_url(settings.REDIS_URL, decode_responses=False)
    return _redis_bytes
