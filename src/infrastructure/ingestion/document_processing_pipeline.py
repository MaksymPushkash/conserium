from typing import Any

from src.domain.value_objects.document_status import DocumentStatus
from src.infrastructure.celery.app import celery_app
from src.infrastructure.celery.tasks.document_processing import (
    _get_document_row,
    _mark_document_status,
    _set_status_sync,
    _step_chunk,
    _step_extract,
    _SyncSession,
)


class DocumentProcessingPipeline:
    def process(self, *, document_id: str, log: Any) -> dict[str, str]:
        with _SyncSession() as session:
            doc = _get_document_row(session, document_id)
            if doc is None:
                log.error("Document not found — skipping")
                return {"document_id": document_id, "status": "NOT_FOUND"}

            _set_status_sync(document_id, "PROCESSING", 10, "Extracting content...")
            _mark_document_status(session, document_id, DocumentStatus.PROCESSING)

            extracted_document = _step_extract(doc, log)

            _set_status_sync(document_id, "PROCESSING", 40, "Splitting into chunks...")
            chunks_data = _step_chunk(extracted_document, log)

            _set_status_sync(document_id, "PROCESSING", 60, "Queued for embedding...")
            celery_app.send_task(
                "src.infrastructure.celery.tasks.embeddings.embed_and_finalize_document",
                args=[document_id, extracted_document.text, chunks_data],
                queue="embeddings",
                routing_key="embeddings",
            )

        log.info("Document processing handed off to embeddings queue")
        return {"document_id": document_id, "status": "EMBEDDING_QUEUED"}
