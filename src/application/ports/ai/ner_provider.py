from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.application.dtos.ingestion_dtos import EntityDTO


class INERProvider(ABC):
    @abstractmethod
    async def extract_entities(self, text: str) -> list[EntityDTO]:
        ...
