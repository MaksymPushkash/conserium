"""ITaskDispatcher — application-layer interface for dispatching background tasks.

This keeps the application layer decoupled from Celery. The infrastructure
implementation just calls process_document.apply_async().
"""

from abc import ABC, abstractmethod
from typing import Any


class ITaskDispatcher(ABC):
    @abstractmethod
    async def dispatch_process_document(self, document_id: str) -> None:
        """Enqueue the document processing pipeline for the given document ID."""

    @abstractmethod
    async def dispatch_process_audio_document(self, document_id: str) -> None:
        """Enqueue audio transcription/chunking work on the HF worker."""

    @abstractmethod
    async def dispatch_process_image_document(self, document_id: str) -> None:
        """Enqueue image OCR/chunking work on the HF worker."""

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
