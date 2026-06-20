from __future__ import annotations

from typing import Any

import structlog

from src.documents.worker import acknowledge_and_process_document_ingestion
from src.worker.dependencies import run_worker_async
from src.worker.document_failure import handle_document_failure
from src.worker.error_handling import classify_error

logger = structlog.get_logger(__name__)


def run_process_document_task(self: Any, document_id: str) -> dict[str, Any]:
    log = logger.bind(document_id=document_id, task_id=self.request.id)
    log.info("Document ingestion task started")

    try:
        result = run_worker_async(
            acknowledge_and_process_document_ingestion(task_id=self.request.id, document_id=document_id)
        )
        if result.get("status") == "SKIPPED":
            log.info("document_processing_outbox_duplicate_task_skipped")
        return result
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
            countdown = min(2**self.request.retries * 60, 3600)
            log.info("retrying_task", countdown=countdown)
            raise self.retry(exc=exc, countdown=countdown) from exc

        log.error("document_ingestion_permanent_failure", reason=reason)
        handle_document_failure(document_id, str(exc), log)
        return {"document_id": document_id, "status": "FAILED", "error": str(exc)}
