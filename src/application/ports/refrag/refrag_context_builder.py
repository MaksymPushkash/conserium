from abc import ABC, abstractmethod

from src.application.dtos.query_dtos import QuerySourceDTO
from src.application.dtos.refrag_dtos import RefragContextPackage


class IRefragContextBuilder(ABC):
    @abstractmethod
    def build_context(self, *, query: str, sources: list[QuerySourceDTO]) -> RefragContextPackage: ...
