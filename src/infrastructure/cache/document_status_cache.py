"""Document processing status cache backed by Redis.

Key schema:  doc:status:{document_id}
Value:       JSON with keys: status, progress, message
TTL:         from settings.REDIS_DOC_STATUS_TTL (default 1 hour)

This lets API consumers poll GET /documents/{id}/status without
touching PostgreSQL during long-running processing.
"""

import json
from uuid import UUID

import structlog
from redis.asyncio import Redis

from src.application.ports.cache.document_status_cache import DocumentStatusDTO, IDocumentStatusCache
from src.core.config import settings

logger = structlog.get_logger(__name__)


def _key(document_id: UUID) -> str:
    return f"doc:status:{document_id}"


class RedisDocumentStatusCache(IDocumentStatusCache):

    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    async def set_status(
        self,
        document_id: UUID,
        status: str,
        progress: int,
        message: str,
    ) -> None:
        payload = json.dumps(
            {
                "document_id": str(document_id),
                "status": status,
                "progress": max(0, min(100, progress)),
                "message": message,
            }
        )
        await self._redis.set(_key(document_id), payload, ex=settings.REDIS_DOC_STATUS_TTL)
        logger.debug(
            "Document status updated",
            document_id=str(document_id),
            status=status,
            progress=progress,
        )

    async def get_status(self, document_id: UUID) -> DocumentStatusDTO | None:
        raw = await self._redis.get(_key(document_id))
        if raw is None:
            return None
        data = json.loads(raw.decode() if isinstance(raw, bytes) else raw)
        return DocumentStatusDTO(
            document_id=UUID(data["document_id"]),
            status=data["status"],
            progress=int(data["progress"]),
            message=data["message"],
        )

    async def delete_status(self, document_id: UUID) -> None:
        await self._redis.delete(_key(document_id))
