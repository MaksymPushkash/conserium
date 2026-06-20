from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.query.schemas import QuerySourceDTO


class IReranker(ABC):
    @abstractmethod
    async def rerank(self, query: str, candidates: list[QuerySourceDTO], top_k: int) -> list[QuerySourceDTO]:
        ...
