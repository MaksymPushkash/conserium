from typing import Any

from src.worker.app import celery_app
from src.worker.task_names import (
    DOCUMENT_EMBED_AND_FINALIZE_TASK,
    DOCUMENT_PROCESS_IMAGE_TASK,
    DOCUMENT_PROCESS_TASK,
    DOCUMENT_PROCESSING_OUTBOX_DRAIN_TASK,
    REPO_SYNC_OUTBOX_DRAIN_TASK,
    REPO_SYNC_RUN_TASK,
)


class CeleryTaskDispatcher:
    async def dispatch_process_document(self, document_id: str, *, task_id: str | None = None) -> None:
        celery_app.send_task(
            DOCUMENT_PROCESS_TASK,
            args=[document_id],
            queue="document_processing",
            routing_key="document_processing",
            task_id=task_id,
        )

    async def dispatch_process_image_document(self, document_id: str) -> None:
        celery_app.send_task(
            DOCUMENT_PROCESS_IMAGE_TASK,
            args=[document_id],
            queue="media_processing",
            routing_key="media_processing",
        )

    async def dispatch_repo_sync_outbox(self) -> None:
        celery_app.send_task(
            REPO_SYNC_OUTBOX_DRAIN_TASK,
            queue="cleanup",
            routing_key="cleanup",
        )

    async def dispatch_repo_sync(self, *, user_id: str, repo_sync_id: str, max_files: int) -> None:
        celery_app.send_task(
            REPO_SYNC_RUN_TASK,
            args=[user_id, repo_sync_id, max_files],
            queue="cleanup",
            routing_key="cleanup",
        )

    async def dispatch_document_processing_outbox(self) -> None:
        celery_app.send_task(
            DOCUMENT_PROCESSING_OUTBOX_DRAIN_TASK,
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
            DOCUMENT_EMBED_AND_FINALIZE_TASK,
            args=[document_id, raw_text, chunks_data, expected_content_hash],
            queue="embeddings",
            routing_key="embeddings",
        )
