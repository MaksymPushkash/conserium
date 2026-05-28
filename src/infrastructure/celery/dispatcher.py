from typing import Any

from src.application.ports.ingestion.task_dispatcher import ITaskDispatcher
from src.infrastructure.celery.app import celery_app

_EMBED_AND_FINALIZE_TASK = "src.infrastructure.celery.tasks.embedding_tasks.embed_and_finalize_document"
_PROCESS_IMAGE_TASK = "src.infrastructure.celery.tasks.media_processing_tasks.process_image_document"
_PROCESS_DOCUMENT_TASK = "src.infrastructure.celery.tasks.document_ingestion_task.process_document"
_DRAIN_REPO_SYNC_OUTBOX_TASK = "src.infrastructure.celery.tasks.repo_sync_tasks.drain_repo_sync_outbox_task"
_DRAIN_DOCUMENT_PROCESSING_OUTBOX_TASK = (
    "src.infrastructure.celery.tasks.document_processing_outbox_tasks.drain_document_processing_outbox_task"
)


class CeleryTaskDispatcher(ITaskDispatcher):
    async def dispatch_process_document(self, document_id: str, *, task_id: str | None = None) -> None:
        celery_app.send_task(
            _PROCESS_DOCUMENT_TASK,
            args=[document_id],
            queue="document_processing",
            routing_key="document_processing",
            task_id=task_id,
        )

    async def dispatch_process_image_document(self, document_id: str) -> None:
        celery_app.send_task(
            _PROCESS_IMAGE_TASK,
            args=[document_id],
            queue="media_processing",
            routing_key="media_processing",
        )

    async def dispatch_repo_sync_outbox(self) -> None:
        celery_app.send_task(
            _DRAIN_REPO_SYNC_OUTBOX_TASK,
            queue="cleanup",
            routing_key="cleanup",
        )

    async def dispatch_document_processing_outbox(self) -> None:
        celery_app.send_task(
            _DRAIN_DOCUMENT_PROCESSING_OUTBOX_TASK,
            queue="cleanup",
            routing_key="cleanup",
        )

    async def dispatch_embed_and_finalize_document(
        self,
        *,
        document_id: str,
        raw_text: str,
        chunks_data: list[dict[str, Any]],
        expected_content_hash: str | None = None,
    ) -> None:
        celery_app.send_task(
            _EMBED_AND_FINALIZE_TASK,
            args=[document_id, raw_text, chunks_data, expected_content_hash],
            queue="embeddings",
            routing_key="embeddings",
        )
