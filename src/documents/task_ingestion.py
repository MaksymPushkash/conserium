from __future__ import annotations

from typing import cast

import structlog

from src.documents.worker import acknowledge_and_process_document_ingestion
from src.worker.document_failure import handle_document_failure
from src.worker.error_handling import RetryableTaskError, classify_error

logger = structlog.get_logger(__name__)
MAX_RETRIES = 3


async def run_process_document_task(*, task_id: str, retry_count: int, document_id: str) -> dict[str, object]:
    log = logger.bind(document_id=document_id, task_id=task_id)
    log.info("Document ingestion task started")

    try:
        raw_result = await acknowledge_and_process_document_ingestion(
            task_id=task_id,
            document_id=document_id,
        )
        result = cast("dict[str, object]", dict(raw_result))
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
            retry_count=retry_count,
            max_retries=MAX_RETRIES,
            error=str(exc),
        )

        if is_retryable and retry_count < MAX_RETRIES - 1:
            log.info("retrying_task")
            raise RetryableTaskError(str(exc)) from exc

        log.error("document_ingestion_permanent_failure", reason=reason)
        handle_document_failure(document_id, str(exc), log)
        return {"document_id": document_id, "status": "FAILED", "error": str(exc)}
