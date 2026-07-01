from __future__ import annotations

from typing import Any

from taskiq import Context, TaskiqDepends

from src.documents.task_embedding import run_embed_and_finalize_document_task
from src.documents.task_enrichment import run_enrich_document_task
from src.documents.task_ingestion import run_process_document_task
from src.documents.task_media import run_process_image_document_task
from src.documents.task_outbox import run_drain_document_processing_outbox_task
from src.worker.app import taskiq_broker
from src.worker.task_names import (
    DOCUMENT_EMBED_AND_FINALIZE_TASK,
    DOCUMENT_ENRICH_TASK,
    DOCUMENT_PROCESS_IMAGE_TASK,
    DOCUMENT_PROCESS_TASK,
    DOCUMENT_PROCESSING_OUTBOX_DRAIN_TASK,
)


def _task_id(context: Context) -> str:
    return context.message.task_id


def _retry_count(context: Context) -> int:
    return int(context.message.labels.get("_retries", 0))


@taskiq_broker.task(
    task_name=DOCUMENT_PROCESS_TASK,
    queue_name="document_processing",
    retry_on_error=True,
    max_retries=3,
    delay=60,
)
async def process_document(
    document_id: str,
    context: Context = TaskiqDepends(),
) -> dict[str, object]:
    return await run_process_document_task(
        task_id=_task_id(context),
        retry_count=_retry_count(context),
        document_id=document_id,
    )


@taskiq_broker.task(
    task_name=DOCUMENT_ENRICH_TASK,
    queue_name="media_processing",
    priority=5,
    timeout=240,
)
async def enrich_document_task(document_id: str) -> dict[str, object]:
    return await run_enrich_document_task(document_id)


@taskiq_broker.task(
    task_name=DOCUMENT_EMBED_AND_FINALIZE_TASK,
    queue_name="embeddings",
    retry_on_error=True,
    max_retries=3,
    delay=60,
    priority=5,
    timeout=150,
)
async def embed_and_finalize_document(
    document_id: str,
    raw_text: str,
    chunks_data: list[dict[str, Any]],
    expected_content_hash: str | None = None,
    context: Context = TaskiqDepends(),
) -> dict[str, str]:
    return await run_embed_and_finalize_document_task(
        task_id=_task_id(context),
        retry_count=_retry_count(context),
        document_id=document_id,
        raw_text=raw_text,
        chunks_data=chunks_data,
        expected_content_hash=expected_content_hash,
        enrichment_task=enrich_document_task,
    )


@taskiq_broker.task(
    task_name=DOCUMENT_PROCESS_IMAGE_TASK,
    queue_name="media_processing",
    retry_on_error=True,
    max_retries=3,
    delay=60,
    timeout=240,
)
async def process_image_document(
    document_id: str,
    context: Context = TaskiqDepends(),
) -> dict[str, str]:
    return await run_process_image_document_task(
        task_id=_task_id(context),
        retry_count=_retry_count(context),
        document_id=document_id,
    )


@taskiq_broker.task(
    task_name=DOCUMENT_PROCESSING_OUTBOX_DRAIN_TASK,
    queue_name="cleanup",
    timeout=360,
    schedule=[
        {
            "schedule_id": "drain-document-processing-outbox",
            "interval": 60.0,
            "labels": {"queue_name": "cleanup"},
        }
    ],
)
async def drain_document_processing_outbox_task(limit: int = 100) -> dict[str, int]:
    return await run_drain_document_processing_outbox_task(limit=limit)


__all__ = [
    "drain_document_processing_outbox_task",
    "embed_and_finalize_document",
    "enrich_document_task",
    "process_document",
    "process_image_document",
]
