from unittest.mock import AsyncMock

import pytest


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
