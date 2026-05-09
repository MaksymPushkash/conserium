from __future__ import annotations

from typing import Any

import structlog

from src.infrastructure.celery.app import celery_app
from src.infrastructure.celery.composition import process_document_ingestion
from src.infrastructure.celery.dependencies import run_worker_async
from src.infrastructure.celery.document_failure import handle_document_failure
from src.infrastructure.celery.error_handling import classify_error

logger = structlog.get_logger(__name__)


@celery_app.task(  # type: ignore[untyped-decorator]
    name="src.infrastructure.celery.tasks.document_ingestion_task.process_document",
    queue="document_processing",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    acks_late=True,
)
def process_document(self: Any, document_id: str) -> dict[str, Any]:
    log = logger.bind(document_id=document_id, task_id=self.request.id)
    log.info("Document ingestion task started")

    try:
        return run_worker_async(process_document_ingestion(document_id))
    except Exception as exc:
        is_retryable, reason = classify_error(exc)

        log.error(
            "document_ingestion_task_error",
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

        log.error("document_ingestion_permanent_failure", reason=reason)
        handle_document_failure(document_id, str(exc), log)
        return {"document_id": document_id, "status": "FAILED", "error": str(exc)}
