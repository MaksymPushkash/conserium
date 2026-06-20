import asyncio
from threading import get_ident
from unittest.mock import AsyncMock

import pytest


async def _successful_coro() -> str:
    return "done"


async def _failing_coro() -> str:
    raise RuntimeError("boom")


async def _runtime_identity() -> tuple[int, int]:
    return id(asyncio.get_running_loop()), get_ident()


def test_run_worker_async_reuses_worker_event_loop() -> None:
    from src.worker.dependencies import run_worker_async, shutdown_worker_runtime

    try:
        result = run_worker_async(_successful_coro())
        first_identity = run_worker_async(_runtime_identity())
        second_identity = run_worker_async(_runtime_identity())
    finally:
        shutdown_worker_runtime()

    assert result == "done"
    assert first_identity == second_identity
    assert first_identity[1] != get_ident()


def test_run_worker_async_propagates_failure_without_stopping_runtime() -> None:
    from src.worker.dependencies import run_worker_async, shutdown_worker_runtime

    try:
        with pytest.raises(RuntimeError, match="boom"):
            run_worker_async(_failing_coro())

        assert run_worker_async(_successful_coro()) == "done"
    finally:
        shutdown_worker_runtime()


def test_shutdown_worker_runtime_disposes_engine(monkeypatch: pytest.MonkeyPatch) -> None:
    import src.worker.dependencies as dependencies

    dispose = AsyncMock()
    monkeypatch.setattr(dependencies, "dispose_worker_engine", dispose)
    dependencies.initialize_worker_runtime()

    dependencies.shutdown_worker_runtime()

    dispose.assert_awaited_once()
    assert dependencies._worker_loop is None
    assert dependencies._worker_thread is None


@pytest.mark.asyncio
async def test_dispose_worker_engine_resets_cached_state(monkeypatch: pytest.MonkeyPatch) -> None:
    import src.worker.dependencies as dependencies

    fake_engine = AsyncMock()
    monkeypatch.setattr(dependencies, "_engine", fake_engine)
    monkeypatch.setattr(dependencies, "_session_factory", object())

    await dependencies.dispose_worker_engine()

    assert dependencies._engine is None
    assert dependencies._session_factory is None
    fake_engine.dispose.assert_awaited_once()
