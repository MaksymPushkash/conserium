from abc import ABC, abstractmethod
from typing import TYPE_CHECKING
from uuid import UUID

if TYPE_CHECKING:
    from src.domain.entities.document_entity import DocumentEntity
    from src.domain.value_objects.document_type import DocumentType


class IDocumentRepository(ABC):
    @abstractmethod
    async def get_by_id(self, document_id: UUID) -> "DocumentEntity | None": ...

    @abstractmethod
    async def get_by_user_id(
        self,
        user_id: UUID,
        *,
        limit: int = 50,
        offset: int = 0,
        document_type: "DocumentType | None" = None,
    ) -> "list[DocumentEntity]": ...

    @abstractmethod
    async def create(self, document: "DocumentEntity") -> None: ...

    @abstractmethod
    async def update(self, document: "DocumentEntity") -> None: ...

    @abstractmethod
    async def delete(self, document_id: UUID) -> None: ...

    @abstractmethod
    async def exists(self, document_id: UUID) -> bool: ...

    @abstractmethod
    async def count_by_user_id(self, user_id: UUID, *, document_type: "DocumentType | None" = None) -> int: ...
