from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class FetchedWebResource:
    title: str | None
    excerpt: str | None


class IWebResourceFetcher(ABC):
    @abstractmethod
    async def fetch(self, url: str) -> FetchedWebResource | None: ...
