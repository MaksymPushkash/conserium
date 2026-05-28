from __future__ import annotations

import logging
from typing import Any

from celery import shared_task

from src.infrastructure.celery.composition import drain_document_processing_outbox
from src.infrastructure.celery.dependencies import run_worker_async

logger = logging.getLogger(__name__)


@shared_task(  # type: ignore[untyped-decorator]
    name="src.infrastructure.celery.tasks.document_processing_outbox_tasks.drain_document_processing_outbox_task",
    queue="cleanup",
    bind=True,
    soft_time_limit=300,
    time_limit=360,
)
def drain_document_processing_outbox_task(self: Any, limit: int = 100) -> dict[str, int]:
    try:
        return run_worker_async(drain_document_processing_outbox(limit=limit))
    except Exception as exc:
        logger.exception("Document processing outbox drain failed: %s", exc)
        return {"claimed": 0, "dispatched": 0, "failed": 1, "permanently_failed": 0}
