from __future__ import annotations

import asyncio
from functools import partial
from tempfile import NamedTemporaryFile

from src.application.ports.ingestion.content_extractor import ExtractedContent, IContentExtractor


class AudioExtractor(IContentExtractor):
    def __init__(self, *, model_name: str = "openai/whisper-base") -> None:
        self._model_name = model_name

    async def extract_from_bytes(
        self,
        data: bytes,
        *,
        filename: str = "",
        language: str | None = None,
    ) -> ExtractedContent:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, partial(self._extract_sync, data, filename))

    async def extract_from_url(self, url: str) -> ExtractedContent:
        raise NotImplementedError("AudioExtractor does not support URL extraction")

    def _extract_sync(self, data: bytes, filename: str) -> ExtractedContent:
        transcript_text = _transcribe_audio_bytes(data, model_name=self._model_name, filename=filename)
        if not transcript_text.strip():
            raise ValueError(f"Audio transcription is empty for {filename or 'uploaded audio'!r}")
        title = filename.rsplit(".", 1)[0] if filename and "." in filename else filename or None
        return ExtractedContent(
            text=transcript_text,
            title=title,
            word_count=len(transcript_text.split()),
        )


def _transcribe_audio_bytes(data: bytes, *, model_name: str, filename: str) -> str:
    try:
        from transformers import pipeline
    except ImportError as exc:
        raise RuntimeError(
            "transformers is required for audio ingestion on the hf_processing worker."
        ) from exc

    suffix = _file_suffix(filename)
    with NamedTemporaryFile(suffix=suffix, delete=True) as temporary_file:
        temporary_file.write(data)
        temporary_file.flush()
        transcriber = pipeline("automatic-speech-recognition", model=model_name)
        result = transcriber(temporary_file.name)

    if isinstance(result, dict):
        text = result.get("text")
        if isinstance(text, str):
            return text.strip()
    raise ValueError("Whisper transcription did not return text")


def _file_suffix(filename: str) -> str:
    if "." not in filename:
        return ".audio"
    return "." + filename.rsplit(".", 1)[1]
