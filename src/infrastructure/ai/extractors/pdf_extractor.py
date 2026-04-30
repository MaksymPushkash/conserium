"""PDF content extractor using pdfplumber.

Responsibilities:
- Extract raw text from PDF bytes, page by page.
- Preserve page numbers on each text span for chunk-level citations.
- Detect language tag from PDF metadata when available.
- Extract title from PDF metadata, falling back to filename.

Design note: extract_from_url is not supported for PDFs — callers must
download the file first and pass the bytes. This avoids having the extractor
own HTTP logic.
"""

import asyncio
import io
from functools import partial

import pdfplumber
import structlog

from src.application.ports.ingestion.content_extractor import ExtractedContent, IContentExtractor

logger = structlog.get_logger(__name__)


_STRIP_CHARS = " \t\r\n\x0c"


class PdfExtractor(IContentExtractor):
    def __init__(self, *, min_page_chars: int = 10) -> None:
        """
        Args:
            min_page_chars: pages with fewer characters after stripping are
                            treated as blank (scanned images, separators, etc.)
        """
        self._min_page_chars = min_page_chars

    async def extract_from_bytes(self, data: bytes, *, filename: str = "") -> ExtractedContent:
        """Run blocking pdfplumber I/O in a thread pool executor."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, partial(self._extract_sync, data, filename))

    async def extract_from_url(self, url: str) -> ExtractedContent:
        raise NotImplementedError(
            "PdfExtractor does not support URL extraction. "
            "Download the PDF first and pass the bytes to extract_from_bytes()."
        )

    def _extract_sync(self, data: bytes, filename: str) -> ExtractedContent:
        pages: dict[int, str] = {}
        meta_title: str | None = None
        meta_language: str | None = None

        try:
            with pdfplumber.open(io.BytesIO(data)) as pdf:
                if pdf.metadata:
                    raw_title = pdf.metadata.get("Title") or pdf.metadata.get("title")
                    if raw_title and isinstance(raw_title, str) and raw_title.strip():
                        meta_title = raw_title.strip()
                    lang = pdf.metadata.get("Language") or pdf.metadata.get("language")
                    if lang and isinstance(lang, str) and lang.strip():
                        meta_language = lang.strip()[:10]

                for page_num, page in enumerate(pdf.pages, start=1):
                    raw_text = page.extract_text(x_tolerance=3, y_tolerance=3) or ""
                    stripped = raw_text.strip(_STRIP_CHARS)
                    if len(stripped) >= self._min_page_chars:
                        pages[page_num] = stripped

        except Exception:
            logger.exception("PdfExtractor: failed to parse PDF", filename=filename)
            raise

        if not pages:
            raise ValueError(f"PDF '{filename}' contains no extractable text (possibly scanned images).")

        full_text = "\n\n".join(pages[p] for p in sorted(pages))
        word_count = len(full_text.split())

        title = meta_title or (filename.removesuffix(".pdf") if filename else None)

        logger.info(
            "PDF extracted",
            filename=filename,
            pages_extracted=len(pages),
            total_pages=len(pages),
            word_count=word_count,
        )

        return ExtractedContent(
            text=full_text,
            title=title,
            language=meta_language,
            word_count=word_count,
            page_count=len(pages),
            pages=pages,
        )
