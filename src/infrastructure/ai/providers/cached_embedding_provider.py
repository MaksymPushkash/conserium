from __future__ import annotations

import hashlib
import json
from typing import TYPE_CHECKING

from src.application.ports.ai.embedding_provider import IEmbeddingProvider
from src.core.config import settings

if TYPE_CHECKING:
    from src.application.ports.cache.cache import ICache


class CachedEmbeddingProvider(IEmbeddingProvider):
    def __init__(self, inner: IEmbeddingProvider, cache: ICache) -> None:
        self._inner = inner
        self._cache = cache

    async def embed_text(self, text: str) -> list[float]:
        embeddings = await self.embed_texts([text])
        return embeddings[0]

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        cached_by_index: dict[int, list[float]] = {}
        misses: list[tuple[int, str, str]] = []

        for index, text in enumerate(texts):
            key = _embedding_cache_key(text)
            cached = await self._cache.get(key)
            if cached is None:
                misses.append((index, key, text))
                continue
            cached_by_index[index] = [float(value) for value in json.loads(cached)]

        if misses:
            missing_embeddings = await self._inner.embed_texts([text for _, _, text in misses])
            for (index, key, _), embedding in zip(misses, missing_embeddings, strict=True):
                cached_by_index[index] = embedding
                await self._cache.set(key, json.dumps(embedding), settings.REDIS_EMBEDDING_CACHE_TTL)

        return [cached_by_index[index] for index in range(len(texts))]


def _embedding_cache_key(text: str) -> str:
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return f"emb:{digest}"
