from __future__ import annotations

import io
import os
from typing import TYPE_CHECKING, Any

from src.settings import settings

if TYPE_CHECKING:
    from PIL.Image import Image as PILImage


def tesseract_config() -> str:
    psm_env = os.getenv("OCR_TESSERACT_PSM")
    tesseract_psm = psm_env if psm_env is not None else "3"
    tesseract_oem = os.getenv("OCR_TESSERACT_OEM", "3")
    return f"--oem {tesseract_oem} --psm {tesseract_psm}"


def tesseract_language_for(language: str | None) -> str:
    requested = (language or settings.OCR_TESSERACT_LANG or "eng").strip().casefold()
    if not requested:
        return "eng"

    normalized = requested.replace("-", "_")
    if normalized in {"uk", "ua", "ukr", "ukrainian", "uk_ua", "ukrainian_ukraine"}:
        return "ukr+eng"
    if normalized in {"en", "eng", "english", "en_us", "en_gb"}:
        return "eng"
    if "+" in normalized:
        parts = [tesseract_language_for(part) for part in normalized.split("+") if part.strip()]
        flattened: list[str] = []
        for part in parts:
            flattened.extend(part.split("+"))
        return "+".join(dict.fromkeys(flattened)) or "eng"
    return normalized


def load_preprocessed_image(image_module: Any, data: bytes) -> PILImage | Any:
    with image_module.open(io.BytesIO(data)) as image:
        img: PILImage | Any = image
        try:
            from PIL import ImageOps

            img = ImageOps.exif_transpose(img)
        except Exception:
            pass

        img = img.convert("RGB")
        if settings.OCR_PREPROCESS_AUTOCONTRAST:
            img = autocontrast(img)
        if settings.OCR_PREPROCESS_DESKEW:
            img = deskew(img)
        img = maybe_upscale(img, min_dimension=settings.OCR_PREPROCESS_MIN_DIMENSION)
        if settings.OCR_PREPROCESS_DENOISE:
            img = denoise(img)
        if settings.OCR_PREPROCESS_THRESHOLD:
            img = threshold(img)
        if settings.OCR_PREPROCESS_SHARPEN:
            img = sharpen(img)
        return img.convert("RGB")


def autocontrast(img: Any) -> Any:
    try:
        from PIL import ImageOps

        return ImageOps.autocontrast(img)
    except Exception:
        return img


def denoise(img: Any) -> Any:
    try:
        from PIL import ImageFilter

        return img.filter(ImageFilter.MedianFilter(size=3))
    except Exception:
        return img


def threshold(img: Any, thresh: int = 128) -> Any:
    try:
        gray = img.convert("L")
        bw = gray.point(lambda p: 255 if p >= thresh else 0)
        return bw.convert("RGB")
    except Exception:
        return img


def deskew(img: Any) -> Any:
    try:
        import pytesseract

        osd = pytesseract.image_to_osd(img)
        for line in osd.splitlines():
            if line.strip().startswith("Rotate:"):
                angle = int(line.split(":", 1)[1].strip())
                if angle and angle % 360 != 0:
                    return img.rotate(-angle, expand=True)
        return img
    except Exception:
        return img


def sharpen(img: Any) -> Any:
    try:
        from PIL import ImageFilter

        return img.filter(ImageFilter.UnsharpMask(radius=1, percent=150, threshold=3))
    except Exception:
        return img


def maybe_upscale(img: Any, min_dimension: int = 800) -> Any:
    try:
        from PIL import Image

        width, height = img.size
        if max(width, height) >= min_dimension:
            return img
        scale = max(1, int(min_dimension / max(width, height)))
        new_size = (width * scale, height * scale)
        return img.resize(new_size, resample=Image.Resampling.BICUBIC)
    except Exception:
        return img
