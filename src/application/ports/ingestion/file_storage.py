from abc import ABC, abstractmethod
from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class StoredFile:
    path: str
    size_bytes: int


class IFileStorage(ABC):
    @abstractmethod
    async def save_document_file(
        self,
        *,
        user_id: UUID,
        filename: str,
        content: bytes,
    ) -> StoredFile: ...
