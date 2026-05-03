from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.application.dtos.refrag_dtos import RefragContextPackage


class IEvalScorer(ABC):
    @abstractmethod
    async def score(
        self,
        *,
        query: str,
        answer: str,
        context: RefragContextPackage,
    ) -> dict[str, float]:
        """Return RAGAS-compatible evaluation scores."""
