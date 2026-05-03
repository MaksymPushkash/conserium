import io
import sys
from types import ModuleType
from typing import Any, cast

import pytest
from PIL import Image, ImageDraw

from src.infrastructure.ai.extractors.image_extractor import ImageExtractor, _tesseract_language_for


@pytest.mark.asyncio
async def test_preprocessing_pipeline_invoked(monkeypatch):
    extractor = ImageExtractor()
    calls: list[str] = []

    def _autocontrast(img: Any) -> Any:
        calls.append("autocontrast")
        return img

    def _upscale(img: Any, min_dimension: int = 800) -> Any:
        calls.append("upscale")
        return img

    def _denoise(img: Any) -> Any:
        calls.append("denoise")
        return img

    def _sharpen(img: Any) -> Any:
        calls.append("sharpen")
        return img

    monkeypatch.setattr(extractor, "_autocontrast", _autocontrast)
    monkeypatch.setattr(extractor, "_maybe_upscale", _upscale)
    monkeypatch.setattr(extractor, "_denoise", _denoise)
    monkeypatch.setattr(extractor, "_sharpen", _sharpen)

    # Provide a lightweight dummy pytesseract module if not installed
    if "pytesseract" not in sys.modules:
        dummy = ModuleType("pytesseract")
        dummy.image_to_string = lambda img, lang=None, config=None: "dummy text"  # type: ignore[attr-defined]
        dummy.TesseractNotFoundError = Exception  # type: ignore[attr-defined]
        dummy.TesseractError = Exception  # type: ignore[attr-defined]
        dummy.image_to_osd = lambda img: "Rotate: 0\n"  # type: ignore[attr-defined]
        sys.modules["pytesseract"] = dummy
    else:
        import pytesseract

        monkeypatch.setattr(pytesseract, "image_to_string", lambda img, lang=None, config=None: "dummy text")

    buf = io.BytesIO()
    Image.new("RGB", (100, 50), color="white").save(buf, format="PNG")
    data = buf.getvalue()

    result = await extractor.extract_from_bytes(data, filename="t.png")

    assert result.text == "dummy text"
    assert result.visual is not None
    assert result.visual["diagram_type"] == result.visual["layout_type"]
    assert {"autocontrast", "upscale", "denoise", "sharpen"}.issubset(set(calls))


def test_visual_analysis_extracts_diagram_structure() -> None:
    image = Image.new("RGB", (300, 120), color="white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((20, 30, 100, 80), outline="black", width=2)
    draw.rectangle((190, 30, 270, 80), outline="black", width=2)
    draw.line((106, 55, 184, 55), fill="black", width=2)
    draw.line((184, 55, 174, 49), fill="black", width=2)
    draw.line((184, 55, 174, 61), fill="black", width=2)

    class _Output:
        DICT = "dict"

    class _FakeTesseract:
        Output = _Output

        @staticmethod
        def image_to_data(img: object, lang: str, output_type: object) -> dict[str, list[object]]:
            return {
                "text": ["Start", "End"],
                "conf": ["95", "93"],
                "left": [44, 222],
                "top": [48, 48],
                "width": [30, 24],
                "height": [12, 12],
            }

    visual = ImageExtractor()._analyze_visual_structure(_FakeTesseract(), image, language="eng")

    assert visual["diagram_type"] == "flowchart"
    assert len(cast("list[object]", visual["diagram_boxes"])) == 2
    assert len(cast("list[object]", visual["diagram_connectors"])) >= 1
    assert len(cast("list[object]", visual["diagram_relationships"])) >= 1


def test_tesseract_language_mapping_supports_ukrainian() -> None:
    assert _tesseract_language_for("uk") == "ukr+eng"
    assert _tesseract_language_for("ukr") == "ukr+eng"
    assert _tesseract_language_for("ukrainian") == "ukr+eng"
    assert _tesseract_language_for("en") == "eng"
    assert _tesseract_language_for("ukr+eng") == "ukr+eng"
