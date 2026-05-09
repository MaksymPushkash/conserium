from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any, Literal, overload

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from src.core.config import settings

if TYPE_CHECKING:
    from collections.abc import Coroutine

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


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
    return Redis.from_url(settings.REDIS_URL, decode_responses=decode_responses)


def run_worker_async[T](coro: Coroutine[Any, Any, T]) -> T:
    async def runner() -> T:
        try:
            return await coro
        finally:
            await dispose_worker_engine()

    return asyncio.run(runner())


async def dispose_worker_engine() -> None:
    global _engine, _session_factory
    engine = _engine
    _engine = None
    _session_factory = None
    if engine is not None:
        await engine.dispose()
