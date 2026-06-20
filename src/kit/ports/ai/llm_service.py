from abc import ABC, abstractmethod
from collections.abc import AsyncIterator

from src.query.schemas import RefragContextPackage


class ILLMService(ABC):
    @abstractmethod
    async def synthesize_answer(self, *, query: str, context: RefragContextPackage) -> str: ...


class IStreamingLLMService(ABC):
    @abstractmethod
    def stream_answer(self, *, query: str, context: RefragContextPackage) -> AsyncIterator[str]: ...
