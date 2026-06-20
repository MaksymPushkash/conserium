from __future__ import annotations

from typing import Any

from src.documents.task_embedding import run_embed_and_finalize_document_task
from src.documents.task_enrichment import run_enrich_document_task
from src.documents.task_ingestion import run_process_document_task
from src.documents.task_media import run_process_image_document_task
from src.documents.task_outbox import run_drain_document_processing_outbox_task
from src.worker.app import celery_app
from src.worker.task_names import (
    DOCUMENT_EMBED_AND_FINALIZE_TASK,
    DOCUMENT_ENRICH_TASK,
    DOCUMENT_PROCESS_IMAGE_TASK,
    DOCUMENT_PROCESS_TASK,
    DOCUMENT_PROCESSING_OUTBOX_DRAIN_TASK,
)


@celery_app.task(  # type: ignore[untyped-decorator]
    name=DOCUMENT_PROCESS_TASK,
    queue="document_processing",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    acks_late=True,
)
def process_document(self: Any, document_id: str) -> dict[str, Any]:
    return run_process_document_task(self, document_id)


@celery_app.task(  # type: ignore[untyped-decorator]
    name=DOCUMENT_ENRICH_TASK,
    queue="media_processing",
    bind=True,
    soft_time_limit=180,
    time_limit=240,
)
def enrich_document_task(self: Any, document_id: str) -> dict[str, object]:
    return run_enrich_document_task(document_id)


@celery_app.task(  # type: ignore[untyped-decorator]
    name=DOCUMENT_EMBED_AND_FINALIZE_TASK,
    queue="embeddings",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    rate_limit="50/m",
    acks_late=True,
    soft_time_limit=120,
    time_limit=150,
)
def embed_and_finalize_document(
    self: Any,
    document_id: str,
    raw_text: str,
    chunks_data: list[dict[str, Any]],
    expected_content_hash: str | None = None,
) -> dict[str, str]:
    return run_embed_and_finalize_document_task(
        self,
        document_id=document_id,
        raw_text=raw_text,
        chunks_data=chunks_data,
        expected_content_hash=expected_content_hash,
        enrichment_task=enrich_document_task,
    )


@celery_app.task(  # type: ignore[untyped-decorator]
    name=DOCUMENT_PROCESS_IMAGE_TASK,
    queue="media_processing",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    acks_late=True,
    soft_time_limit=180,
    time_limit=240,
)
def process_image_document(self: Any, document_id: str) -> dict[str, str]:
    return run_process_image_document_task(self, document_id)


@celery_app.task(  # type: ignore[untyped-decorator]
    name=DOCUMENT_PROCESSING_OUTBOX_DRAIN_TASK,
    queue="cleanup",
    bind=True,
    soft_time_limit=300,
    time_limit=360,
)
def drain_document_processing_outbox_task(self: Any, limit: int = 100) -> dict[str, int]:
    return run_drain_document_processing_outbox_task(limit=limit)


__all__ = [
    "drain_document_processing_outbox_task",
    "embed_and_finalize_document",
    "enrich_document_task",
    "process_document",
    "process_image_document",
]
