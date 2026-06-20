from __future__ import annotations

import logging

from src.documents.worker import enrich_document
from src.worker.dependencies import run_worker_async

logger = logging.getLogger(__name__)


def run_enrich_document_task(document_id: str) -> dict[str, object]:
    try:
        return run_worker_async(enrich_document(document_id))
    except Exception as exc:
        logger.exception("Document enrichment failed for doc %s: %s", document_id, exc)
        return {
            "status": "failed",
            "document_id": document_id,
            "error": str(exc),
        }
