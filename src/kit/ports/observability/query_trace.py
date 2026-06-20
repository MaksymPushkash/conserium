from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.query.agents.state import ConseriumQueryState


class IQueryTracer(ABC):
    @abstractmethod
    async def trace_query(self, state: ConseriumQueryState) -> str | None:
        """Record query trace data and return an external trace id when available."""
