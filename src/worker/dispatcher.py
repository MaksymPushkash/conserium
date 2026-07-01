from typing import Any


class TaskiqTaskDispatcher:
    async def dispatch_process_document(
        self,
        document_id: str,
        *,
        task_id: str | None = None,
        priority: int | None = None,
    ) -> None:
        from src.documents.tasks import process_document

        kicker = process_document.kicker().with_labels(queue_name="document_processing")
        if task_id is not None:
            kicker = kicker.with_task_id(task_id)
        if priority is not None:
            kicker = kicker.with_labels(priority=priority)
        await kicker.kiq(document_id)

    async def dispatch_process_image_document(self, document_id: str) -> None:
        from src.documents.tasks import process_image_document

        await process_image_document.kicker().with_labels(queue_name="media_processing").kiq(document_id)

    async def dispatch_repo_sync_outbox(self) -> None:
        from src.repo_syncs.tasks import drain_repo_sync_outbox_task

        await drain_repo_sync_outbox_task.kicker().with_labels(queue_name="cleanup").kiq()

    async def dispatch_repo_sync(self, *, user_id: str, repo_sync_id: str, max_files: int) -> None:
        from src.repo_syncs.tasks import run_repo_sync_task

        await run_repo_sync_task.kicker().with_labels(queue_name="cleanup").kiq(user_id, repo_sync_id, max_files)

    async def dispatch_document_processing_outbox(self) -> None:
        from src.documents.tasks import drain_document_processing_outbox_task

        await drain_document_processing_outbox_task.kicker().with_labels(queue_name="cleanup").kiq()

    async def dispatch_embed_and_finalize_document(
        self,
        *,
        document_id: str,
        raw_text: str,
        chunks_data: list[dict[str, Any]],
        expected_content_hash: str | None = None,
    ) -> None:
        from src.documents.tasks import embed_and_finalize_document

        await embed_and_finalize_document.kicker().with_labels(queue_name="embeddings").kiq(
            document_id,
            raw_text,
            chunks_data,
            expected_content_hash,
        )
