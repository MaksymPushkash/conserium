"""Unit tests for RedisDocumentStatusCache."""
from __future__ import annotations

import json
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.application.ports.cache.document_status_cache import DocumentStatusDTO
from src.infrastructure.cache.document_status_cache import RedisDocumentStatusCache


def _make_cache(redis_mock: AsyncMock) -> RedisDocumentStatusCache:
    return RedisDocumentStatusCache(redis=redis_mock)


class TestRedisDocumentStatusCache:

    @pytest.fixture
    def redis(self) -> AsyncMock:
        return AsyncMock()

    async def test_set_status_stores_json(self, redis: AsyncMock) -> None:
        cache = _make_cache(redis)
        doc_id = uuid4()

        await cache.set_status(doc_id, "PROCESSING", 50, "Generating embeddings…")

        redis.set.assert_awaited_once()
        call_args = redis.set.call_args
        key = call_args.args[0]
        payload = json.loads(call_args.args[1])

        assert key == f"doc:status:{doc_id}"
        assert payload["status"] == "PROCESSING"
        assert payload["progress"] == 50
        assert payload["message"] == "Generating embeddings…"
        assert payload["document_id"] == str(doc_id)

    async def test_set_status_clamps_progress(self, redis: AsyncMock) -> None:
        cache = _make_cache(redis)
        doc_id = uuid4()

        await cache.set_status(doc_id, "PROCESSING", 150, "Too high")
        payload = json.loads(redis.set.call_args.args[1])
        assert payload["progress"] == 100

        redis.reset_mock()
        await cache.set_status(doc_id, "PROCESSING", -5, "Too low")
        payload = json.loads(redis.set.call_args.args[1])
        assert payload["progress"] == 0

    async def test_get_status_returns_dto(self, redis: AsyncMock) -> None:
        cache = _make_cache(redis)
        doc_id = uuid4()

        redis.get.return_value = json.dumps({
            "document_id": str(doc_id),
            "status": "READY",
            "progress": 100,
            "message": "Processing complete.",
        }).encode()

        result = await cache.get_status(doc_id)

        assert result is not None
        assert isinstance(result, DocumentStatusDTO)
        assert result.document_id == doc_id
        assert result.status == "READY"
        assert result.progress == 100
        assert result.message == "Processing complete."

    async def test_get_status_returns_none_when_missing(self, redis: AsyncMock) -> None:
        cache = _make_cache(redis)
        redis.get.return_value = None

        result = await cache.get_status(uuid4())

        assert result is None

    async def test_delete_status_calls_redis_delete(self, redis: AsyncMock) -> None:
        cache = _make_cache(redis)
        doc_id = uuid4()

        await cache.delete_status(doc_id)

        redis.delete.assert_awaited_once_with(f"doc:status:{doc_id}")

    async def test_set_uses_configured_ttl(self, redis: AsyncMock) -> None:
        from src.core.config import settings
        cache = _make_cache(redis)

        await cache.set_status(uuid4(), "QUEUED", 0, "Queued")

        call_kwargs = redis.set.call_args.kwargs
        assert call_kwargs.get("ex") == settings.REDIS_DOC_STATUS_TTL
