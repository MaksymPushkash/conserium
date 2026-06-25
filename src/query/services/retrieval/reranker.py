from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.query.schemas import QuerySource


class Reranker(ABC):
    @abstractmethod
    async def rerank(self, query: str, candidates: list[QuerySource], top_k: int) -> list[QuerySource]: ...
