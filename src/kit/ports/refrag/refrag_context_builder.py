from abc import ABC, abstractmethod

from src.query.schemas import QuerySourceDTO, RefragContextPackage


class IRefragContextBuilder(ABC):
    @abstractmethod
    def build_context(self, *, query: str, sources: list[QuerySourceDTO]) -> RefragContextPackage: ...
