from __future__ import annotations

from typing import Any

import structlog

from src.domain.value_objects.document_status import DocumentStatus
from src.infrastructure.celery.app import celery_app
from src.infrastructure.celery.tasks.document_processing import (
    _get_document_row,
    _handle_failure,
    _mark_document_status,
    _set_status_sync,
    _step_embed,
    _step_finalize,
    _SyncSession,
)

logger = structlog.get_logger(__name__)


@celery_app.task(  # type: ignore[untyped-decorator]
    name="src.infrastructure.celery.tasks.embeddings.embed_and_finalize_document",
    queue="embeddings",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    rate_limit="50/m",
    acks_late=True,
)
def embed_and_finalize_document(
    self: Any,
    document_id: str,
    raw_text: str,
    chunks_data: list[dict[str, Any]],
) -> dict[str, str]:
    log = logger.bind(document_id=document_id, task_id=self.request.id)
    log.info("Embedding task started", chunks=len(chunks_data))

    try:
        with _SyncSession() as session:
            doc = _get_document_row(session, document_id)
            if doc is None:
                log.error("Document not found — skipping embeddings")
                return {"document_id": document_id, "status": "NOT_FOUND"}

            _set_status_sync(document_id, "PROCESSING", 70, "Generating embeddings…")
            _mark_document_status(session, document_id, DocumentStatus.PROCESSING)
            embedded_chunks = _step_embed(chunks_data, log)

            _set_status_sync(document_id, "PROCESSING", 90, "Saving to database…")
            _step_finalize(session, document_id, doc, raw_text, embedded_chunks, log)

        _set_status_sync(document_id, "READY", 100, "Processing complete.")
        log.info("Embedding task completed")
        return {"document_id": document_id, "status": "READY"}

    except Exception as exc:
        log.exception("Embedding task failed", error=str(exc))
        if self.request.retries >= self.max_retries:
            _handle_failure(document_id, str(exc), log)
            return {"document_id": document_id, "status": "FAILED"}
        raise self.retry(exc=exc) from exc
