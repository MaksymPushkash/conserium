from __future__ import annotations

from typing import Any

import structlog

from src.documents.worker import process_image_document as process_image_document_worker
from src.worker.dependencies import run_worker_async
from src.worker.document_failure import handle_document_failure

logger = structlog.get_logger(__name__)


def run_process_image_document_task(self: Any, document_id: str) -> dict[str, str]:
    log = logger.bind(document_id=document_id, task_id=self.request.id)
    log.info("Media image processing task started")

    try:
        result = run_worker_async(process_image_document_worker(document_id))
        log.info("Media image processing task completed", status=result["status"])
        return result
    except Exception as exc:
        log.exception("Media image processing task failed", error=str(exc))
        if self.request.retries >= self.max_retries:
            handle_document_failure(document_id, str(exc), log)
            return {"document_id": document_id, "status": "FAILED"}
        raise self.retry(exc=exc) from exc
