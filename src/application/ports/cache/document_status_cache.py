from abc import ABC, abstractmethod
from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class DocumentStatusDTO:
    """Snapshot of async processing progress for a document."""

    document_id: UUID
    status: str
    progress: int
    message: str


class IDocumentStatusCache(ABC):
    """Interface for reading / writing document processing status in Redis."""

    @abstractmethod
    async def set_status(
        self,
        document_id: UUID,
        status: str,
        progress: int,
        message: str,
    ) -> None: ...

    @abstractmethod
    async def get_status(self, document_id: UUID) -> DocumentStatusDTO | None: ...

    @abstractmethod
    async def delete_status(self, document_id: UUID) -> None: ...
