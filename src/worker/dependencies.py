from __future__ import annotations

import asyncio
from threading import Lock, Thread
from typing import TYPE_CHECKING, Any, Literal, overload

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from src.settings import settings

if TYPE_CHECKING:
    from collections.abc import Coroutine

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None
_runtime_lock = Lock()
_worker_loop: asyncio.AbstractEventLoop | None = None
_worker_thread: Thread | None = None


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
    initialize_worker_runtime()
    loop = _worker_loop
    if loop is None:
        raise RuntimeError("worker event loop is not initialized")
    return asyncio.run_coroutine_threadsafe(coro, loop).result()


def initialize_worker_runtime(**_: object) -> None:
    global _worker_loop, _worker_thread
    with _runtime_lock:
        if _worker_loop is not None and _worker_thread is not None and _worker_thread.is_alive():
            return

        loop = asyncio.new_event_loop()
        thread = Thread(target=_run_worker_loop, args=(loop,), name="conserium-worker-asyncio", daemon=True)
        _worker_loop = loop
        _worker_thread = thread
        thread.start()


def shutdown_worker_runtime(**_: object) -> None:
    global _worker_loop, _worker_thread
    with _runtime_lock:
        loop = _worker_loop
        thread = _worker_thread
        _worker_loop = None
        _worker_thread = None

    if loop is None or thread is None:
        return

    asyncio.run_coroutine_threadsafe(dispose_worker_engine(), loop).result()
    loop.call_soon_threadsafe(loop.stop)
    thread.join()


def _run_worker_loop(loop: asyncio.AbstractEventLoop) -> None:
    asyncio.set_event_loop(loop)
    try:
        loop.run_forever()
    finally:
        loop.run_until_complete(loop.shutdown_asyncgens())
        loop.close()


async def dispose_worker_engine() -> None:
    global _engine, _session_factory
    engine = _engine
    _engine = None
    _session_factory = None
    if engine is not None:
        await engine.dispose()
