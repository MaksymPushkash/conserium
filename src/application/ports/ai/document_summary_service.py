from abc import ABC, abstractmethod


class IDocumentSummaryService(ABC):
    @abstractmethod
    async def summarize_document(self, *, title: str, text: str) -> str | None: ...
