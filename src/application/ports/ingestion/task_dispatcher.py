from abc import ABC, abstractmethod
from typing import Any


class ITaskDispatcher(ABC):
    @abstractmethod
    async def dispatch_process_document(self, document_id: str, *, task_id: str | None = None) -> None:
        """Enqueue the document processing pipeline for the given document ID."""

    @abstractmethod
    async def dispatch_process_image_document(self, document_id: str) -> None:
        """Enqueue image OCR/chunking work on the media worker."""

    @abstractmethod
    async def dispatch_repo_sync_outbox(self) -> None:
        """Enqueue repo sync outbox draining work."""

    @abstractmethod
    async def dispatch_document_processing_outbox(self) -> None:
        """Enqueue document processing outbox draining work."""

    @abstractmethod
    async def dispatch_embed_and_finalize_document(
        self,
        *,
        document_id: str,
        raw_text: str,
        chunks_data: list[dict[str, Any]],
        expected_content_hash: str | None = None,
    ) -> None:
        """Enqueue embedding/finalization work for an already extracted document."""
