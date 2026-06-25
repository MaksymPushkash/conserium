from abc import ABC, abstractmethod
from collections.abc import AsyncIterator

from src.query.schemas import RefragContextPackage


class LLMService(ABC):
    @abstractmethod
    async def synthesize_answer(self, *, query: str, context: RefragContextPackage) -> str: ...


class StreamingLLMService(ABC):
    @abstractmethod
    def stream_answer(self, *, query: str, context: RefragContextPackage) -> AsyncIterator[str]: ...
