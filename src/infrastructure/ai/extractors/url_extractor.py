import asyncio
import ipaddress
import socket
from functools import partial
from http.client import HTTPResponse
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

import structlog
import trafilatura
from trafilatura.settings import use_config

from src.application.ports.ingestion.content_extractor import ExtractedContent, IContentExtractor

logger = structlog.get_logger(__name__)

_TRAFILATURA_CONFIG = use_config()
_TRAFILATURA_CONFIG.set("DEFAULT", "SLEEP_TIME", "0")
_ALLOWED_SCHEMES = frozenset({"http", "https"})
_MAX_REDIRECTS = 5
_MAX_RESPONSE_BYTES = 2_000_000
_USER_AGENT = "CortexBot/0.1"


class _NoRedirectHandler(HTTPRedirectHandler):
    def redirect_request(
        self,
        req: Request,
        fp: Any,
        code: int,
        msg: str,
        headers: Any,
        newurl: str,
    ) -> None:
        return None


_URL_OPENER = build_opener(_NoRedirectHandler())


class UnsafeUrlError(ValueError):
    pass


class UrlExtractor(IContentExtractor):
    def __init__(self, *, timeout_seconds: float = 15.0) -> None:
        self._timeout_seconds = timeout_seconds

    async def extract_from_url(self, url: str) -> ExtractedContent:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, partial(self._fetch_and_extract_sync, url))

    async def extract_from_bytes(
        self,
        data: bytes,
        *,
        filename: str = "",
        language: str | None = None,
    ) -> ExtractedContent:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, partial(self._extract_from_html_sync, data, filename))


    def _fetch_and_extract_sync(self, url: str) -> ExtractedContent:
        try:
            downloaded = _fetch_url_safely(url, timeout_seconds=self._timeout_seconds)
        except Exception:
            logger.exception("UrlExtractor: failed to fetch URL", url=url)
            raise

        return self._extract_from_html_sync(downloaded, url)

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


def _fetch_url_safely(url: str, *, timeout_seconds: float) -> bytes:
    current_url = _validate_public_url(url)
    for _ in range(_MAX_REDIRECTS + 1):
        request = Request(current_url, headers={"User-Agent": _USER_AGENT})
        try:
            with _URL_OPENER.open(request, timeout=timeout_seconds) as response:
                _validate_response(response, current_url)
                return _read_limited(response)
        except HTTPError as exc:
            if exc.code in {301, 302, 303, 307, 308}:
                location = exc.headers.get("Location")
                if location is None:
                    raise ValueError(f"Redirect response missing Location header for URL: {current_url!r}") from exc
                current_url = _validate_public_url(urljoin(current_url, location))
                continue
            raise ValueError(f"Failed to download content from URL: {current_url!r}") from exc
        except URLError as exc:
            raise ValueError(f"Failed to download content from URL: {current_url!r}") from exc
    raise ValueError(f"Too many redirects while fetching URL: {url!r}")


def _validate_response(response: HTTPResponse, url: str) -> None:
    content_length = response.headers.get("Content-Length")
    if content_length is not None and int(content_length) > _MAX_RESPONSE_BYTES:
        raise ValueError(f"URL response is too large: {url!r}")
    content_type = response.headers.get("Content-Type", "")
    if content_type and not _is_supported_content_type(content_type):
        raise ValueError(f"URL response is not HTML/text content: {url!r}")


def _read_limited(response: HTTPResponse) -> bytes:
    data = response.read(_MAX_RESPONSE_BYTES + 1)
    if len(data) > _MAX_RESPONSE_BYTES:
        raise ValueError("URL response exceeded maximum allowed size")
    return data


def _is_supported_content_type(content_type: str) -> bool:
    lowered = content_type.casefold()
    return any(kind in lowered for kind in ("text/html", "text/plain", "application/xhtml+xml", "application/xml"))


def _validate_public_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme.casefold() not in _ALLOWED_SCHEMES:
        raise UnsafeUrlError("URL scheme must be http or https")
    if not parsed.hostname:
        raise UnsafeUrlError("URL host is required")
    _validate_public_host(parsed.hostname)
    return url


def _validate_public_host(hostname: str) -> None:
    try:
        addresses = socket.getaddrinfo(hostname, None, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise UnsafeUrlError(f"Could not resolve URL host: {hostname!r}") from exc

    if not addresses:
        raise UnsafeUrlError(f"Could not resolve URL host: {hostname!r}")

    for address in addresses:
        ip = ipaddress.ip_address(address[4][0])
        if not ip.is_global:
            raise UnsafeUrlError(f"URL host resolves to a non-public address: {hostname!r}")
