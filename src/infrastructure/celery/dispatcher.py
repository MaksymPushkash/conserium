from typing import Any

from src.application.ports.ingestion.task_dispatcher import ITaskDispatcher
from src.infrastructure.celery.app import celery_app

_EMBED_AND_FINALIZE_TASK = "src.infrastructure.celery.tasks.embeddings.embed_and_finalize_document"
_PROCESS_AUDIO_TASK = "src.infrastructure.celery.tasks.hf_processing.process_audio_document"
_PROCESS_IMAGE_TASK = "src.infrastructure.celery.tasks.hf_processing.process_image_document"
_PROCESS_DOCUMENT_TASK = "src.infrastructure.celery.tasks.document_processing.process_document"


class CeleryTaskDispatcher(ITaskDispatcher):
    async def dispatch_process_document(self, document_id: str) -> None:
        celery_app.send_task(
            _PROCESS_DOCUMENT_TASK,
            args=[document_id],
            queue="document_processing",
            routing_key="document_processing",
        )

    async def dispatch_process_audio_document(self, document_id: str) -> None:
        celery_app.send_task(
            _PROCESS_AUDIO_TASK,
            args=[document_id],
            queue="hf_processing",
            routing_key="hf_processing",
        )

    async def dispatch_process_image_document(self, document_id: str) -> None:
        celery_app.send_task(
            _PROCESS_IMAGE_TASK,
            args=[document_id],
            queue="hf_processing",
            routing_key="hf_processing",
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
