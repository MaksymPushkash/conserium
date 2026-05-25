from abc import ABC, abstractmethod
from uuid import UUID

from src.application.dtos.compare_dtos import CompareResultDTO


class ICompareRepository(ABC):
    @abstractmethod
    async def create(self, result: CompareResultDTO) -> CompareResultDTO: ...

    @abstractmethod
    async def get_by_id(self, comparison_id: UUID) -> CompareResultDTO | None: ...

    @abstractmethod
    async def list_by_user_id(
        self,
        *,
        user_id: UUID,
        collection_id: UUID | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[CompareResultDTO]: ...

    @abstractmethod
    async def count_by_user_id(
        self,
        *,
        user_id: UUID,
        collection_id: UUID | None = None,
    ) -> int: ...

    @abstractmethod
    async def delete(self, comparison_id: UUID) -> None: ...
