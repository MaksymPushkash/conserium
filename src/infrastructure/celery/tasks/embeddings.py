from __future__ import annotations

import asyncio
from typing import Any

import structlog

from src.application.use_cases.documents.process_document_embeddings_use_case import (
    ProcessDocumentEmbeddingsUseCase,
)
from src.infrastructure.ai.providers.cached_embedding_provider import CachedEmbeddingProvider
from src.infrastructure.ai.providers.openai_embedding_provider import OpenAIEmbeddingProvider
from src.infrastructure.cache.document_status_cache import RedisDocumentStatusCache
from src.infrastructure.cache.redis_cache import RedisCache
from src.infrastructure.celery.app import celery_app
from src.infrastructure.celery.dependencies import get_worker_redis, get_worker_session_factory
from src.infrastructure.celery.error_handling import classify_error
from src.infrastructure.celery.tasks.document_processing import (
    _handle_failure,
)
from src.infrastructure.celery.tasks.enrichment import (
    enrich_document_task,
)
from src.infrastructure.database.unit_of_work import SQLAlchemyUnitOfWork

logger = structlog.get_logger(__name__)


@celery_app.task(  # type: ignore[untyped-decorator]
    name="src.infrastructure.celery.tasks.embeddings.embed_and_finalize_document",
    queue="embeddings",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    rate_limit="50/m",
    acks_late=True,
)
def embed_and_finalize_document(
    self: Any,
    document_id: str,
    raw_text: str,
    chunks_data: list[dict[str, Any]],
    expected_content_hash: str | None = None,
) -> dict[str, str]:
    log = logger.bind(document_id=document_id, task_id=self.request.id)
    log.info("Embedding task started", chunks=len(chunks_data))

    try:
        result = asyncio.run(
            _run_process_document_embeddings_use_case(
                document_id=document_id,
                raw_text=raw_text,
                chunks_data=chunks_data,
                expected_content_hash=expected_content_hash,
            )
        )
        log.info("Embedding task completed", status=result["status"])

        # Dispatch enrichment orchestration after embeddings are ready.
        if result["status"] == "READY" and raw_text:
            try:
                log.info("Dispatching enrichment tasks", document_id=document_id)
                enrich_document_task.apply_async(args=[document_id], priority=5)
            except Exception as e:
                log.warning("Failed to dispatch enrichment tasks, but document is READY", error=str(e))

        return result
    except Exception as exc:
        is_retryable, reason = classify_error(exc)

        log.error(
            "embedding_task_error",
            error_type=type(exc).__name__,
            error_reason=reason,
            is_retryable=is_retryable,
            retry_count=self.request.retries,
            max_retries=self.max_retries,
            error=str(exc),
        )

        if is_retryable and self.request.retries < self.max_retries:
            countdown = min(2 ** self.request.retries * 60, 3600)
            log.info("retrying_task", countdown=countdown)
            raise self.retry(exc=exc, countdown=countdown) from exc

        log.error("embedding_task_permanent_failure", reason=reason)
        _handle_failure(document_id, str(exc), log)
        return {"document_id": document_id, "status": "FAILED", "error": str(exc)}


async def _run_process_document_embeddings_use_case(
    *,
    document_id: str,
    raw_text: str,
    chunks_data: list[dict[str, Any]],
    expected_content_hash: str | None = None,
) -> dict[str, str]:
    factory = get_worker_session_factory()
    redis = get_worker_redis(decode_responses=False)

    async with factory() as session:
        use_case = ProcessDocumentEmbeddingsUseCase(
            uow=SQLAlchemyUnitOfWork(session),
            status_cache=RedisDocumentStatusCache(redis),
            embedding_provider=CachedEmbeddingProvider(
                OpenAIEmbeddingProvider(),
                RedisCache(redis),
            ),
        )
        result = await use_case(
            document_id=document_id,
            raw_text=raw_text,
            chunks_data=chunks_data,
            expected_content_hash=expected_content_hash,
        )
        return {"document_id": result.document_id, "status": result.status}
