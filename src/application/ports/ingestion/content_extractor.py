from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class ExtractedContent:
    """Result of extracting text from a document source."""

    text: str
    title: str | None = None
    language: str | None = None
    word_count: int = 0
    page_count: int | None = None  # PDF-only
    # Per-page text keyed by 1-based page number (PDF-only, optional)
    pages: dict[int, str] = field(default_factory=dict)
    visual: dict[str, object] | None = None

    def __post_init__(self) -> None:
        if not self.text.strip():
            raise ValueError("Extracted content text cannot be empty")
        if self.page_count is not None and self.page_count < 1:
            raise ValueError("page_count must be at least 1")


class IContentExtractor(ABC):
    """Interface for extracting plain text from a document source.

    Concrete implementations live in infrastructure and are unaware
    of Celery, FastAPI, or SQLAlchemy.
    """

    @abstractmethod
    async def extract_from_bytes(
        self,
        data: bytes,
        *,
        filename: str = "",
        language: str | None = None,
    ) -> ExtractedContent:
        """Extract content from raw bytes (e.g. an uploaded file)."""

    @abstractmethod
    async def extract_from_url(self, url: str) -> ExtractedContent:
        """Extract content from a remote URL."""
