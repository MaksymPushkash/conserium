from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.application.agents.query.state import CortexQueryState


class IQueryTracer(ABC):
    @abstractmethod
    async def trace_query(self, state: CortexQueryState) -> str | None:
        """Record query trace data and return an external trace id when available."""
