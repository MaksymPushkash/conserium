from __future__ import annotations

import asyncio
from functools import partial
from typing import TYPE_CHECKING, Any, ClassVar

from src.application.ports.ai.ner_provider import INERProvider

if TYPE_CHECKING:
    from src.application.dtos.ingestion_dtos import EntityDTO


class HFNERProvider(INERProvider):
    _pipeline: ClassVar[Any | None] = None

    async def extract_entities(self, text: str) -> list[EntityDTO]:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, partial(self._extract_sync, text))

    def _extract_sync(self, text: str) -> list[EntityDTO]:
        if HFNERProvider._pipeline is None:
            from transformers import pipeline

            HFNERProvider._pipeline = pipeline(
                "token-classification",
                model="dslim/bert-base-NER",
                aggregation_strategy="simple",
            )

        entities = HFNERProvider._pipeline(text[:2048])
        return [
            {"text": str(entity["word"]), "label": str(entity["entity_group"])}
            for entity in entities
            if str(entity.get("word", "")).strip()
        ]
