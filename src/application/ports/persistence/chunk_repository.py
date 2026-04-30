from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING
from uuid import UUID

if TYPE_CHECKING:
    from src.domain.entities.chunk_entity import ChunkEntity


@dataclass(frozen=True, slots=True)
class ChunkSearchResult:
    chunk: "ChunkEntity"
    document_title: str | None
    score: float | None = None


class IChunkRepository(ABC):
    @abstractmethod
    async def get_by_id(self, chunk_id: UUID) -> "ChunkEntity | None": ...

    @abstractmethod
    async def get_by_document_id(self, document_id: UUID) -> "list[ChunkEntity]": ...

    @abstractmethod
    async def create_batch(self, chunks: "list[ChunkEntity]") -> None: ...

    @abstractmethod
    async def delete_by_document_id(self, document_id: UUID) -> None: ...

    @abstractmethod
    async def semantic_search(
        self,
        embedding: list[float],
        user_id: UUID,
        *,
        limit: int = 10,
        collection_id: UUID | None = None,
    ) -> "list[ChunkEntity]": ...

    @abstractmethod
    async def hybrid_search(
        self,
        *,
        query: str,
        embedding: list[float],
        user_id: UUID,
        limit: int = 10,
        collection_id: UUID | None = None,
    ) -> list[ChunkSearchResult]: ...
