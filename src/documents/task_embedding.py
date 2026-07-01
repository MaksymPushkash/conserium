from __future__ import annotations

from typing import Any

import structlog

from src.documents.worker import process_document_embeddings
from src.worker.document_failure import handle_document_failure
from src.worker.error_handling import RetryableTaskError, classify_error

logger = structlog.get_logger(__name__)
MAX_RETRIES = 3


async def run_embed_and_finalize_document_task(
    *,
    task_id: str,
    retry_count: int,
    document_id: str,
    raw_text: str,
    chunks_data: list[dict[str, Any]],
    expected_content_hash: str | None,
    enrichment_task: Any,
) -> dict[str, str]:
    log = logger.bind(document_id=document_id, task_id=task_id)
    log.info("Embedding task started", chunks=len(chunks_data))

    try:
        result = await process_document_embeddings(
            document_id=document_id,
            raw_text=raw_text,
            chunks_data=chunks_data,
            expected_content_hash=expected_content_hash,
        )
        log.info("Embedding task completed", status=result["status"])

        if result["status"] == "READY" and raw_text:
            try:
                log.info("Dispatching enrichment task", document_id=document_id)
                await enrichment_task.kicker().with_labels(priority=5).kiq(document_id)
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
            retry_count=retry_count,
            max_retries=MAX_RETRIES,
            error=str(exc),
        )

        if is_retryable and retry_count < MAX_RETRIES - 1:
            log.info("retrying_task")
            raise RetryableTaskError(str(exc)) from exc

        log.error("embedding_task_permanent_failure", reason=reason)
        handle_document_failure(document_id, str(exc), log)
        return {"document_id": document_id, "status": "FAILED", "error": str(exc)}
