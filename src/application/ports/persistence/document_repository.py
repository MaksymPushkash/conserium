from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING
from uuid import UUID

if TYPE_CHECKING:
    from src.domain.entities.document_entity import DocumentEntity
    from src.domain.value_objects.document_status import DocumentStatus
    from src.domain.value_objects.document_type import DocumentType


@dataclass(frozen=True, slots=True)
class RelatedDocumentRecord:
    document: "DocumentEntity"
    reasons: list[str]
    relationship_score: int


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
        collection_id: UUID | None = None,
        status: "DocumentStatus | None" = None,
    ) -> "list[DocumentEntity]": ...

    @abstractmethod
    async def create(self, document: "DocumentEntity") -> None: ...

    @abstractmethod
    async def update(self, document: "DocumentEntity") -> None: ...

    @abstractmethod
    async def delete(self, document_id: UUID) -> None: ...

    @abstractmethod
    async def add_manual_tags(self, *, document_id: UUID, user_id: UUID, tag_names: list[str]) -> None: ...

    @abstractmethod
    async def exists(self, document_id: UUID) -> bool: ...

    @abstractmethod
    async def count_by_user_id(
        self,
        user_id: UUID,
        *,
        document_type: "DocumentType | None" = None,
        collection_id: UUID | None = None,
        status: "DocumentStatus | None" = None,
    ) -> int: ...

    @abstractmethod
    async def count_by_status(
        self,
        user_id: UUID,
        *,
        collection_id: UUID | None = None,
    ) -> "dict[DocumentStatus, int]": ...

    @abstractmethod
    async def get_collection_documents_with_status_counts(
        self,
        user_id: UUID,
        *,
        collection_id: UUID,
        limit: int = 200,
    ) -> "tuple[list[DocumentEntity], dict[DocumentStatus, int]]": ...

    @abstractmethod
    async def get_related_documents(
        self,
        *,
        user_id: UUID,
        document_id: UUID,
        limit: int = 5,
    ) -> list[RelatedDocumentRecord]: ...
