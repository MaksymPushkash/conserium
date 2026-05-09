from __future__ import annotations

from typing import Any

import structlog

from src.infrastructure.celery.app import celery_app
from src.infrastructure.celery.composition import process_document_embeddings
from src.infrastructure.celery.dependencies import run_worker_async
from src.infrastructure.celery.document_failure import handle_document_failure
from src.infrastructure.celery.error_handling import classify_error
from src.infrastructure.celery.tasks.enrichment_tasks import enrich_document_task

logger = structlog.get_logger(__name__)


@celery_app.task(  # type: ignore[untyped-decorator]
    name="src.infrastructure.celery.tasks.embedding_tasks.embed_and_finalize_document",
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
        result = run_worker_async(
            process_document_embeddings(
                document_id=document_id,
                raw_text=raw_text,
                chunks_data=chunks_data,
                expected_content_hash=expected_content_hash,
            )
        )
        log.info("Embedding task completed", status=result["status"])

        if result["status"] == "READY" and raw_text:
            try:
                log.info("Dispatching enrichment task", document_id=document_id)
                enrich_document_task.apply_async(args=[document_id], priority=5)
            except Exception as exc:
                log.warning("Failed to dispatch enrichment task, but document is READY", error=str(exc))

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
        handle_document_failure(document_id, str(exc), log)
        return {"document_id": document_id, "status": "FAILED", "error": str(exc)}
