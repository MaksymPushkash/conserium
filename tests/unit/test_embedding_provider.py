from unittest.mock import patch

import pytest

from src.domain.entities.chunk_entity import ChunkEntity
from src.infrastructure.ai.providers.openai_embedding_provider import OpenAIEmbeddingProvider


def test_openai_embedding_provider_rejects_mismatched_dimension_config() -> None:
    with patch(
        "src.infrastructure.ai.providers.openai_embedding_provider.settings.OPENAI_EMBEDDING_DIMENSIONS",
        ChunkEntity.EMBEDDING_DIMENSIONS + 1,
    ):
        with pytest.raises(ValueError, match="OPENAI_EMBEDDING_DIMENSIONS"):
            OpenAIEmbeddingProvider()


async def test_openai_embedding_provider_requires_api_key() -> None:
    with patch("src.infrastructure.ai.providers.openai_embedding_provider.settings.OPENAI_API_KEY", ""):
        provider = OpenAIEmbeddingProvider()

        with pytest.raises(ValueError, match="OPENAI_API_KEY"):
            await provider.embed_texts(["hello"])
