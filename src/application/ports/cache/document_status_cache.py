from abc import ABC, abstractmethod
from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class DocumentStatusDTO:
    document_id: UUID
    status: str
    progress: int
    message: str


class IDocumentStatusCache(ABC):
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
