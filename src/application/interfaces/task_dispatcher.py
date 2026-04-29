"""ITaskDispatcher — application-layer interface for dispatching background tasks.

This keeps the application layer decoupled from Celery. The infrastructure
implementation just calls process_document.apply_async().
"""

from abc import ABC, abstractmethod


class ITaskDispatcher(ABC):
    @abstractmethod
    async def dispatch_process_document(self, document_id: str) -> None:
        """Enqueue the document processing pipeline for the given document ID."""
