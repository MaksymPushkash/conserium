from __future__ import annotations

import asyncio
from functools import partial
from typing import TYPE_CHECKING, Any, ClassVar

from src.application.ports.ai.classifier_provider import IClassifierProvider

if TYPE_CHECKING:
    from src.application.dtos.ingestion_dtos import CategoryDTO


class HFClassifierProvider(IClassifierProvider):
    _pipeline: ClassVar[Any | None] = None
    _labels: ClassVar[list[str]] = ["business", "technical", "educational", "personal", "news", "other"]

    async def classify(self, text: str) -> list[CategoryDTO]:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, partial(self._classify_sync, text))

    def _classify_sync(self, text: str) -> list[CategoryDTO]:
        if HFClassifierProvider._pipeline is None:
            from transformers import pipeline

            HFClassifierProvider._pipeline = pipeline(
                "zero-shot-classification",
                model="facebook/bart-large-mnli",
            )

        result = HFClassifierProvider._pipeline(text[:2048], self._labels, multi_label=True)
        return [
            {"label": str(label), "score": float(score)}
            for label, score in zip(result["labels"], result["scores"], strict=True)
        ]
