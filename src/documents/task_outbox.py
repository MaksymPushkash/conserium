from __future__ import annotations

import logging

from src.documents.worker import drain_document_processing_outbox
from src.worker.dependencies import run_worker_async

logger = logging.getLogger(__name__)


def run_drain_document_processing_outbox_task(limit: int = 100) -> dict[str, int]:
    try:
        return run_worker_async(drain_document_processing_outbox(limit=limit))
    except Exception as exc:
        logger.exception("Document processing outbox drain failed: %s", exc)
        return {"claimed": 0, "dispatched": 0, "failed": 1, "permanently_failed": 0}
