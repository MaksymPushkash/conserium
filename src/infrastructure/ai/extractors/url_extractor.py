"""URL content extractor using trafilatura.

Responsibilities:
- Download a web page and extract its main content (stripping nav, ads,
  footers, boilerplate).
- Return clean prose text suitable for chunking and embedding.
- Detect language from HTTP headers or HTML meta tags.
- Fall back gracefully when trafilatura cannot extract meaningful content.

Design note: extract_from_bytes accepts raw HTML bytes for cases where the
caller has already downloaded the page (e.g. testing, cached responses).
"""

import asyncio
from functools import partial

import structlog
import trafilatura
from trafilatura.settings import use_config

from src.application.interfaces.content_extractor import ExtractedContent, IContentExtractor

logger = structlog.get_logger(__name__)

_TRAFILATURA_CONFIG = use_config()
_TRAFILATURA_CONFIG.set("DEFAULT", "SLEEP_TIME", "0")


class UrlExtractor(IContentExtractor):
    def __init__(self, *, timeout_seconds: float = 15.0) -> None:
        self._timeout_seconds = timeout_seconds

    async def extract_from_url(self, url: str) -> ExtractedContent:
        """Fetch and extract content from a URL, running I/O in a thread pool."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, partial(self._fetch_and_extract_sync, url))

    async def extract_from_bytes(self, data: bytes, *, filename: str = "") -> ExtractedContent:
        """Extract content from raw HTML bytes (e.g. for tests or cached pages)."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, partial(self._extract_from_html_sync, data, filename))

    # Internal sync helpers (run in thread pool executor)
    def _fetch_and_extract_sync(self, url: str) -> ExtractedContent:
        try:
            downloaded = trafilatura.fetch_url(url, config=_TRAFILATURA_CONFIG)
        except Exception:
            logger.exception("UrlExtractor: failed to fetch URL", url=url)
            raise

        if downloaded is None:
            raise ValueError(f"Failed to download content from URL: {url!r}")

        return self._extract_from_html_sync(downloaded.encode() if isinstance(downloaded, str) else downloaded, url)

    def _extract_from_html_sync(self, data: bytes, source_hint: str = "") -> ExtractedContent:
        html = data.decode("utf-8", errors="replace")

        result = trafilatura.extract(
            html,
            include_comments=False,
            include_tables=True,
            no_fallback=False,
            favor_precision=False,
            config=_TRAFILATURA_CONFIG,
            output_format="txt",
        )

        if not result or not result.strip():
            raise ValueError(
                f"trafilatura could not extract meaningful content from {source_hint!r}. "
                "The page may be behind a paywall, require JavaScript, or contain only images."
            )

        metadata = trafilatura.extract_metadata(html)
        title: str | None = None
        language: str | None = None

        if metadata:
            if metadata.title and metadata.title.strip():
                title = metadata.title.strip()
            if metadata.language and metadata.language.strip():
                language = metadata.language.strip()[:10]

        word_count = len(result.split())

        logger.info(
            "URL extracted",
            source=source_hint,
            word_count=word_count,
            title=title,
            language=language,
        )

        return ExtractedContent(
            text=result,
            title=title,
            language=language,
            word_count=word_count,
            page_count=None,
        )
