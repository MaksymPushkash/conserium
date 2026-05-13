from __future__ import annotations

from typing import Any

import structlog

from src.infrastructure.celery.app import celery_app
from src.infrastructure.celery.composition import process_image_document as process_image_document_use_case
from src.infrastructure.celery.dependencies import run_worker_async
from src.infrastructure.celery.document_failure import handle_document_failure

logger = structlog.get_logger(__name__)


@celery_app.task(  # type: ignore[untyped-decorator]
    name="src.infrastructure.celery.tasks.media_processing_tasks.process_image_document",
    queue="media_processing",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    acks_late=True,
    soft_time_limit=180,
    time_limit=240,
)
def process_image_document(self: Any, document_id: str) -> dict[str, str]:
    log = logger.bind(document_id=document_id, task_id=self.request.id)
    log.info("Media image processing task started")

    try:
        result = run_worker_async(process_image_document_use_case(document_id))
        log.info("Media image processing task completed", status=result["status"])
        return result
    except Exception as exc:
        log.exception("Media image processing task failed", error=str(exc))
        if self.request.retries >= self.max_retries:
            handle_document_failure(document_id, str(exc), log)
            return {"document_id": document_id, "status": "FAILED"}
        raise self.retry(exc=exc) from exc
