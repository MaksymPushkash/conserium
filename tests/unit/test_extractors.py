"""Unit tests for content extractors."""

from __future__ import annotations

import textwrap
from email.message import Message
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError

import pytest

from src.documents.extraction import ExtractedContent

# ---------------------------------------------------------------------------
# ExtractedContent dataclass validation
# ---------------------------------------------------------------------------


class TestExtractedContent:
    def test_valid_content(self) -> None:
        ec = ExtractedContent(text="Hello world", title="Test", word_count=2)
        assert ec.text == "Hello world"
        assert ec.word_count == 2
        assert ec.page_count is None
        assert ec.pages == {}

    def test_empty_text_raises(self) -> None:
        with pytest.raises(ValueError, match="cannot be empty"):
            ExtractedContent(text="   ")

    def test_invalid_page_count_raises(self) -> None:
        with pytest.raises(ValueError, match="page_count"):
            ExtractedContent(text="hello", page_count=0)

    def test_pages_preserved(self) -> None:
        ec = ExtractedContent(text="p1\n\np2", pages={1: "p1", 2: "p2"})
        assert ec.pages[1] == "p1"
        assert ec.pages[2] == "p2"


# ---------------------------------------------------------------------------
# PdfExtractor
# ---------------------------------------------------------------------------


class TestPdfExtractor:
    def _make_fake_pdf_bytes(self) -> bytes:
        """Return minimal valid-looking bytes — we mock pdfplumber, not parse real PDF."""
        return b"%PDF-1.4 fake"

    def _mock_pdf(self, pages_text: list[str]) -> MagicMock:
        """Build a pdfplumber mock returning given text per page."""
        mock_pdf = MagicMock()
        mock_pages = []
        for text in pages_text:
            mock_page = MagicMock()
            mock_page.extract_text.return_value = text
            mock_pages.append(mock_page)
        mock_pdf.pages = mock_pages
        mock_pdf.metadata = {"Title": "My PDF Title"}
        mock_pdf.__enter__ = MagicMock(return_value=mock_pdf)
        mock_pdf.__exit__ = MagicMock(return_value=False)
        return mock_pdf

    @pytest.mark.asyncio
    async def test_extract_single_page(self) -> None:
        from src.kit.ai.extractors.pdf_extractor import PdfExtractor

        extractor = PdfExtractor()
        fake_pdf = self._mock_pdf(["Hello world this is page one content here."])

        with patch("pdfplumber.open", return_value=fake_pdf):
            result = await extractor.extract_from_bytes(b"fake", filename="test.pdf")

        assert "Hello world" in result.text
        assert result.title == "My PDF Title"
        assert result.page_count == 1
        assert result.word_count > 0
        assert 1 in result.pages

    @pytest.mark.asyncio
    async def test_extract_multi_page(self) -> None:
        from src.kit.ai.extractors.pdf_extractor import PdfExtractor

        extractor = PdfExtractor()
        pages = [
            "First page content with enough text here.",
            "Second page content also has some text.",
        ]
        fake_pdf = self._mock_pdf(pages)

        with patch("pdfplumber.open", return_value=fake_pdf):
            result = await extractor.extract_from_bytes(b"fake", filename="multi.pdf")

        assert result.page_count == 2
        assert 1 in result.pages
        assert 2 in result.pages
        # Full text contains both pages joined by double newline
        assert "First page" in result.text
        assert "Second page" in result.text

    @pytest.mark.asyncio
    async def test_blank_pages_skipped(self) -> None:
        from src.kit.ai.extractors.pdf_extractor import PdfExtractor

        extractor = PdfExtractor()
        pages = [
            "Real content page with enough characters.",
            "  \n  ",  # blank page
            "Another real page with real content here.",
        ]
        fake_pdf = self._mock_pdf(pages)

        with patch("pdfplumber.open", return_value=fake_pdf):
            result = await extractor.extract_from_bytes(b"fake")

        # Only 2 pages have real text
        assert result.page_count == 2

    @pytest.mark.asyncio
    async def test_no_text_raises(self) -> None:
        from src.kit.ai.extractors.pdf_extractor import PdfExtractor

        extractor = PdfExtractor()
        fake_pdf = self._mock_pdf(["   ", "  \n"])  # all blank

        with patch("pdfplumber.open", return_value=fake_pdf), pytest.raises(ValueError, match="no extractable text"):
            await extractor.extract_from_bytes(b"fake", filename="scanned.pdf")

    @pytest.mark.asyncio
    async def test_title_falls_back_to_filename(self) -> None:
        from src.kit.ai.extractors.pdf_extractor import PdfExtractor

        extractor = PdfExtractor()
        fake_pdf = self._mock_pdf(["Some real content that is long enough."])
        fake_pdf.metadata = {}  # no Title in metadata

        with patch("pdfplumber.open", return_value=fake_pdf):
            result = await extractor.extract_from_bytes(b"fake", filename="my_document.pdf")

        assert result.title == "my_document"

    @pytest.mark.asyncio
    async def test_extract_from_url_raises(self) -> None:
        from src.kit.ai.extractors.pdf_extractor import PdfExtractor

        extractor = PdfExtractor()
        with pytest.raises(NotImplementedError):
            await extractor.extract_from_url("https://example.com/doc.pdf")


# ---------------------------------------------------------------------------
# UrlExtractor
# ---------------------------------------------------------------------------


class TestUrlExtractor:
    _SAMPLE_HTML = textwrap.dedent("""\
        <html>
        <head><title>Test Article</title></head>
        <body>
        <nav>Nav garbage</nav>
        <article>
            <h1>Main Title</h1>
            <p>This is the main article content that trafilatura should extract.
            It has multiple sentences and enough words to be considered real content.</p>
        </article>
        <footer>Footer garbage</footer>
        </body>
        </html>
    """).encode()

    @pytest.mark.asyncio
    async def test_extract_from_bytes_success(self) -> None:
        from src.kit.ai.extractors.url_extractor import UrlExtractor

        extractor = UrlExtractor()

        # Patch trafilatura to return controlled output
        with (
            patch("trafilatura.extract", return_value="Main Title\nThis is the main article content."),
            patch("trafilatura.extract_metadata") as mock_meta,
        ):
            mock_meta.return_value = MagicMock(title="Test Article", language="en")
            result = await extractor.extract_from_bytes(self._SAMPLE_HTML, filename="test.html")

        assert "Main Title" in result.text
        assert result.title == "Test Article"
        assert result.language == "en"
        assert result.page_count is None  # URLs have no pages

    @pytest.mark.asyncio
    async def test_extract_from_bytes_empty_result_raises(self) -> None:
        from src.kit.ai.extractors.url_extractor import UrlExtractor

        extractor = UrlExtractor()

        with patch("trafilatura.extract", return_value=None), pytest.raises(ValueError, match="could not extract"):
            await extractor.extract_from_bytes(self._SAMPLE_HTML)

    @pytest.mark.asyncio
    async def test_extract_from_url_success(self) -> None:
        from src.kit.ai.extractors.url_extractor import UrlExtractor

        extractor = UrlExtractor()

        with (
            patch(
                "src.kit.ai.extractors.url_extractor._fetch_url_safely",
                return_value=b"<html><body>Real content here for testing purposes.</body></html>",
            ),
            patch("trafilatura.extract", return_value="Real content here for testing purposes."),
            patch("trafilatura.extract_metadata") as mock_meta,
        ):
            mock_meta.return_value = MagicMock(title="Page Title", language="en")
            result = await extractor.extract_from_url("https://example.com/article")

        assert "Real content" in result.text
        assert result.title == "Page Title"

    @pytest.mark.asyncio
    async def test_fetch_url_failure_raises(self) -> None:
        from src.kit.ai.extractors.url_extractor import UrlExtractor

        extractor = UrlExtractor()

        with (
            patch(
                "src.kit.ai.extractors.url_extractor._fetch_url_safely",
                side_effect=ValueError("Failed to download"),
            ),
            pytest.raises(ValueError, match="Failed to download"),
        ):
            await extractor.extract_from_url("https://example.com/missing")

    @pytest.mark.asyncio
    async def test_extract_from_url_blocks_non_http_scheme(self) -> None:
        from src.kit.ai.extractors.url_extractor import UnsafeUrlError, UrlExtractor

        extractor = UrlExtractor()

        with pytest.raises(UnsafeUrlError, match="scheme"):
            await extractor.extract_from_url("file:///etc/passwd")

    @pytest.mark.asyncio
    async def test_extract_from_url_blocks_private_hosts(self) -> None:
        from src.kit.ai.extractors.url_extractor import UnsafeUrlError, UrlExtractor

        extractor = UrlExtractor()

        with (
            patch("socket.getaddrinfo", return_value=[(0, 0, 0, "", ("127.0.0.1", 0))]),
            pytest.raises(UnsafeUrlError, match="non-public"),
        ):
            await extractor.extract_from_url("https://example.com/private")

    @pytest.mark.asyncio
    async def test_extract_from_url_blocks_redirect_to_private_host(self) -> None:
        from src.kit.ai.extractors.url_extractor import UnsafeUrlError, UrlExtractor

        extractor = UrlExtractor()
        headers = Message()
        headers["Location"] = "http://127.0.0.1/private"
        redirect_error = HTTPError(
            url="https://example.com/article",
            code=302,
            msg="Found",
            hdrs=headers,
            fp=None,
        )

        def _fake_getaddrinfo(
            hostname: str,
            *_args: object,
            **_kwargs: object,
        ) -> list[tuple[int, int, int, str, tuple[str, int]]]:
            if hostname == "example.com":
                return [(0, 0, 0, "", ("93.184.216.34", 0))]
            if hostname == "127.0.0.1":
                return [(0, 0, 0, "", ("127.0.0.1", 0))]
            raise AssertionError(f"Unexpected hostname: {hostname}")

        with (
            patch("socket.getaddrinfo", side_effect=_fake_getaddrinfo),
            patch("src.kit.ai.extractors.url_extractor._URL_OPENER.open", side_effect=redirect_error),
            pytest.raises(UnsafeUrlError, match="non-public"),
        ):
            await extractor.extract_from_url("https://example.com/article")

    @pytest.mark.asyncio
    async def test_language_truncated_to_10_chars(self) -> None:
        from src.kit.ai.extractors.url_extractor import UrlExtractor

        extractor = UrlExtractor()

        with (
            patch("trafilatura.extract", return_value="Some content here for testing."),
            patch("trafilatura.extract_metadata") as mock_meta,
        ):
            mock_meta.return_value = MagicMock(title=None, language="en-US-and-more-stuff")
            result = await extractor.extract_from_bytes(self._SAMPLE_HTML)

        assert len(result.language or "") <= 10


# ---------------------------------------------------------------------------
# YoutubeExtractor
# ---------------------------------------------------------------------------


class TestYoutubeExtractor:
    @pytest.mark.asyncio
    async def test_extract_from_url_success(self) -> None:
        from src.kit.ai.extractors.youtube_extractor import YoutubeExtractor

        extractor = YoutubeExtractor()

        with patch(
            "src.kit.ai.extractors.youtube_extractor._fetch_transcript",
            return_value=[
                {"text": "First line", "start": 0.0, "duration": 1.0},
                {"text": "Second line", "start": 1.0, "duration": 1.0},
            ],
        ):
            result = await extractor.extract_from_url("https://youtu.be/abc123")

        assert result.title == "YouTube abc123"
        assert result.word_count == 4
        assert "First line" in result.text
        assert "Second line" in result.text

    @pytest.mark.asyncio
    async def test_extract_from_url_rejects_non_youtube_url(self) -> None:
        from src.kit.ai.extractors.youtube_extractor import YoutubeExtractor

        extractor = YoutubeExtractor()

        with pytest.raises(ValueError, match="Unsupported YouTube URL"):
            await extractor.extract_from_url("https://example.com/video")

    def test_transcript_to_raw_items_supports_new_api_result(self) -> None:
        from src.kit.ai.extractors.youtube_extractor import _transcript_to_raw_items

        class _FetchedTranscript:
            def to_raw_data(self) -> list[dict[str, object]]:
                return [{"text": "Fetched line", "start": 0.0, "duration": 1.5}]

        assert _transcript_to_raw_items(_FetchedTranscript()) == [
            {"text": "Fetched line", "start": 0.0, "duration": 1.5}
        ]

    def test_transcript_to_raw_items_supports_iterable_snippets(self) -> None:
        from dataclasses import dataclass

        from src.kit.ai.extractors.youtube_extractor import _transcript_to_raw_items

        @dataclass
        class _Snippet:
            text: str
            start: float
            duration: float

        assert _transcript_to_raw_items([_Snippet("Snippet line", 2.0, 3.5)]) == [
            {"text": "Snippet line", "start": 2.0, "duration": 3.5}
        ]
