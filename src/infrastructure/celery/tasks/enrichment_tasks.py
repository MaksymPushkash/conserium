from __future__ import annotations

import logging
from typing import Any

from celery import shared_task

from src.infrastructure.celery.composition import enrich_document
from src.infrastructure.celery.dependencies import run_worker_async

logger = logging.getLogger(__name__)


@shared_task(  # type: ignore[untyped-decorator]
    name="src.infrastructure.celery.tasks.enrichment_tasks.enrich_document_task",
    queue="media_processing",
    bind=True,
)
def enrich_document_task(self: Any, document_id: str) -> dict[str, object]:
    try:
        return run_worker_async(enrich_document(document_id))
    except Exception as exc:
        logger.exception("Document enrichment failed for doc %s: %s", document_id, exc)
        return {
            "status": "failed",
            "document_id": document_id,
            "error": str(exc),
        }
