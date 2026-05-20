from abc import ABC, abstractmethod
from uuid import UUID

from src.application.dtos.conflict_dtos import ConflictClaimRecordDTO, PersistedConflictRecordDTO


class IConflictRepository(ABC):
    @abstractmethod
    async def replace_claims_for_documents(
        self,
        *,
        user_id: UUID,
        document_ids: list[UUID],
        claims: list[ConflictClaimRecordDTO],
    ) -> None: ...

    @abstractmethod
    async def replace_conflicts(
        self,
        *,
        user_id: UUID,
        collection_id: UUID | None,
        conflicts: list[PersistedConflictRecordDTO],
    ) -> None: ...
