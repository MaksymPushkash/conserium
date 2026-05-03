from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.application.dtos.ingestion_dtos import CategoryDTO


class IClassifierProvider(ABC):
    @abstractmethod
    async def classify(self, text: str) -> list[CategoryDTO]:
        ...
