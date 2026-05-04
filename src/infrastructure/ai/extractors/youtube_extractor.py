from __future__ import annotations

import asyncio
from functools import partial
from typing import Any, cast
from urllib.parse import parse_qs, urlparse

from src.application.ports.ingestion.content_extractor import ExtractedContent, IContentExtractor


class YoutubeExtractor(IContentExtractor):
    async def extract_from_bytes(
        self,
        data: bytes,
        *,
        filename: str = "",
        language: str | None = None,
    ) -> ExtractedContent:
        raise NotImplementedError("YoutubeExtractor does not support byte extraction")

    async def extract_from_url(self, url: str) -> ExtractedContent:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, partial(self._extract_sync, url))

    def _extract_sync(self, url: str) -> ExtractedContent:
        video_id = _extract_video_id(url)
        transcript_items = _fetch_transcript(video_id)
        transcript_text = "\n".join(text for item in transcript_items if (text := _transcript_text(item)))
        if not transcript_text.strip():
            raise ValueError(f"YouTube transcript is empty for video {video_id!r}")
        return ExtractedContent(
            text=transcript_text,
            title=f"YouTube {video_id}",
            word_count=len(transcript_text.split()),
        )


def _fetch_transcript(video_id: str) -> list[dict[str, object]]:
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
    except ImportError as exc:
        raise RuntimeError(
            "youtube-transcript-api is required for YouTube ingestion. "
            "Add it to the environment before ingesting YouTube documents."
        ) from exc

    api_class = cast("Any", YouTubeTranscriptApi)
    get_transcript = getattr(api_class, "get_transcript", None)
    if callable(get_transcript):
        return list(get_transcript(video_id))

    api = api_class()
    fetched_transcript = api.fetch(video_id)
    return _transcript_to_raw_items(fetched_transcript)


def _transcript_to_raw_items(transcript: Any) -> list[dict[str, object]]:
    to_raw_data = getattr(transcript, "to_raw_data", None)
    if callable(to_raw_data):
        return list(to_raw_data())

    return [_snippet_to_raw_item(snippet) for snippet in transcript]


def _snippet_to_raw_item(snippet: object) -> dict[str, object]:
    return {
        "text": getattr(snippet, "text", ""),
        "start": getattr(snippet, "start", 0.0),
        "duration": getattr(snippet, "duration", 0.0),
    }


def _transcript_text(item: dict[str, object]) -> str:
    text = item.get("text")
    if isinstance(text, str):
        return text.strip()
    return ""


def _extract_video_id(url: str) -> str:
    parsed = urlparse(url)
    host = (parsed.hostname or "").casefold()

    if host in {"youtu.be", "www.youtu.be"}:
        video_id = parsed.path.strip("/")
        if video_id:
            return video_id

    if host.endswith("youtube.com"):
        if parsed.path == "/watch":
            query_video_id = parse_qs(parsed.query).get("v", [])
            if query_video_id and query_video_id[0]:
                return query_video_id[0]

        path_parts = [part for part in parsed.path.split("/") if part]
        if len(path_parts) >= 2 and path_parts[0] in {"embed", "shorts", "live"} and path_parts[1]:
            return path_parts[1]

    raise ValueError(f"Unsupported YouTube URL: {url!r}")
