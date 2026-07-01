from __future__ import annotations

import structlog

from src.documents.worker import process_image_document as process_image_document_worker
from src.worker.document_failure import handle_document_failure
from src.worker.error_handling import RetryableTaskError

logger = structlog.get_logger(__name__)
MAX_RETRIES = 3


async def run_process_image_document_task(*, task_id: str, retry_count: int, document_id: str) -> dict[str, str]:
    log = logger.bind(document_id=document_id, task_id=task_id)
    log.info("Media image processing task started")

    try:
        result = await process_image_document_worker(document_id)
        log.info("Media image processing task completed", status=result["status"])
        return result
    except Exception as exc:
        log.exception("Media image processing task failed", error=str(exc))
        if retry_count >= MAX_RETRIES - 1:
            handle_document_failure(document_id, str(exc), log)
            return {"document_id": document_id, "status": "FAILED"}
        raise RetryableTaskError(str(exc)) from exc
