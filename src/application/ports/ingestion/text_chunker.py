from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.application.dtos.ingestion_dtos import TextChunkDTO


class ITextChunker(ABC):
    @abstractmethod
    def chunk_text(self, text: str) -> list[TextChunkDTO]: ...
