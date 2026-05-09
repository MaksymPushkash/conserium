from unittest.mock import AsyncMock, patch

import pytest


async def _successful_coro() -> str:
    return "done"


async def _failing_coro() -> str:
    raise RuntimeError("boom")


def test_run_worker_async_disposes_engine_after_success() -> None:
    from src.infrastructure.celery.dependencies import run_worker_async

    with patch("src.infrastructure.celery.dependencies.dispose_worker_engine", new_callable=AsyncMock) as dispose:
        result = run_worker_async(_successful_coro())

    assert result == "done"
    dispose.assert_awaited_once()


def test_run_worker_async_disposes_engine_after_failure() -> None:
    from src.infrastructure.celery.dependencies import run_worker_async

    with (
        patch("src.infrastructure.celery.dependencies.dispose_worker_engine", new_callable=AsyncMock) as dispose,
        pytest.raises(RuntimeError, match="boom"),
    ):
        run_worker_async(_failing_coro())

    dispose.assert_awaited_once()


@pytest.mark.asyncio
async def test_dispose_worker_engine_resets_cached_state(monkeypatch: pytest.MonkeyPatch) -> None:
    import src.infrastructure.celery.dependencies as dependencies

    fake_engine = AsyncMock()
    monkeypatch.setattr(dependencies, "_engine", fake_engine)
    monkeypatch.setattr(dependencies, "_session_factory", object())

    await dependencies.dispose_worker_engine()

    assert dependencies._engine is None
    assert dependencies._session_factory is None
    fake_engine.dispose.assert_awaited_once()
