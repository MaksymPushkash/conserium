from __future__ import annotations

import asyncio
from functools import partial
from typing import Any

from src.kit.ai.extractors.image_preprocessing import (
    load_preprocessed_image,
    tesseract_config,
    tesseract_language_for,
)
from src.kit.ai.extractors.image_visual_analysis import ImageVisualAnalyzer
from src.kit.ports.ingestion.content_extractor import ExtractedContent, IContentExtractor


class ImageExtractor(IContentExtractor):
    def __init__(self, visual_analyzer: ImageVisualAnalyzer | None = None) -> None:
        self._visual_analyzer = visual_analyzer or ImageVisualAnalyzer()

    async def extract_from_bytes(
        self,
        data: bytes,
        *,
        filename: str = "",
        language: str | None = None,
    ) -> ExtractedContent:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, partial(self._extract_sync, data, filename, language))

    async def extract_from_url(self, url: str) -> ExtractedContent:
        raise NotImplementedError("ImageExtractor does not support URL extraction")

    def _extract_sync(self, data: bytes, filename: str, language: str | None) -> ExtractedContent:
        try:
            from PIL import Image
        except ImportError as exc:
            raise RuntimeError("Pillow is required for image OCR ingestion.") from exc

        try:
            import pytesseract
        except ImportError as exc:
            raise RuntimeError("pytesseract is required for image OCR ingestion.") from exc

        config = tesseract_config()
        ocr_language = tesseract_language_for(language)

        try:
            img = load_preprocessed_image(Image, data)
            text, visual, ocr_warning = self._ocr_image(
                pytesseract=pytesseract,
                img=img,
                config=config,
                language=ocr_language,
            )
        except pytesseract.TesseractNotFoundError as exc:
            raise RuntimeError("The tesseract binary is required for image OCR ingestion.") from exc
        except pytesseract.TesseractError as exc:
            raise RuntimeError("Tesseract failed to OCR the image.") from exc

        if not text.strip():
            raise ValueError(f"Image OCR is empty for {filename or 'uploaded image'!r}")

        title = filename.rsplit(".", 1)[0] if filename and "." in filename else filename or None
        visual["ocr_language"] = ocr_language
        if ocr_warning:
            visual["ocr_warning"] = ocr_warning
        return ExtractedContent(
            text=text.strip(),
            title=title,
            word_count=len(text.split()),
            language=language,
            visual=visual,
        )

    def _ocr_image(
        self,
        *,
        pytesseract: Any,
        img: Any,
        config: str,
        language: str,
    ) -> tuple[str, dict[str, object], str | None]:
        try:
            text = pytesseract.image_to_string(img, lang=language, config=config)
            visual = self._visual_analyzer.analyze(pytesseract, img, language=language)
            return text, visual, None
        except pytesseract.TesseractError:
            if language == "eng":
                raise

        text = pytesseract.image_to_string(img, lang="eng", config=config)
        visual = self._visual_analyzer.analyze(pytesseract, img, language="eng")
        warning = f"OCR language {language!r} failed or is unavailable; retried with 'eng'."
        return text, visual, warning

