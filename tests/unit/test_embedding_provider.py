from unittest.mock import AsyncMock, patch

import pytest

from src.core.startup_checks import validate_startup_settings
from src.domain.entities.chunk_entity import ChunkEntity
from src.infrastructure.ai.providers.openai_embedding_provider import OpenAIEmbeddingProvider


def test_openai_embedding_provider_rejects_mismatched_dimension_config() -> None:
    with patch(
        "src.infrastructure.ai.providers.openai_embedding_provider.settings.OPENAI_EMBEDDING_DIMENSIONS",
        ChunkEntity.EMBEDDING_DIMENSIONS + 1,
    ), pytest.raises(ValueError, match="OPENAI_EMBEDDING_DIMENSIONS"):
        OpenAIEmbeddingProvider()


async def test_openai_embedding_provider_requires_api_key() -> None:
    with patch("src.infrastructure.ai.providers.openai_embedding_provider.settings.OPENAI_API_KEY", ""):
        provider = OpenAIEmbeddingProvider()

        with pytest.raises(ValueError, match="OPENAI_API_KEY"):
            await provider.embed_texts(["hello"])


async def test_openai_embedding_provider_closes_client() -> None:
    provider = OpenAIEmbeddingProvider()
    client = AsyncMock()
    provider._client = client

    await provider.aclose()

    client.close.assert_awaited_once()
    assert provider._client is None


async def test_openai_embedding_provider_configures_client_timeout_and_retries() -> None:
    with (
        patch("src.infrastructure.ai.providers.openai_embedding_provider.settings.OPENAI_API_KEY", "test-key"),
        patch("src.infrastructure.ai.providers.openai_embedding_provider.AsyncOpenAI") as client_cls,
    ):
        client = AsyncMock()
        client.embeddings.create.return_value.data = [
            type("Embedding", (), {"embedding": [0.1] * ChunkEntity.EMBEDDING_DIMENSIONS})()
        ]
        client_cls.return_value = client
        provider = OpenAIEmbeddingProvider()

        await provider.embed_texts(["hello"])

        client_cls.assert_called_once()
        assert client_cls.call_args.kwargs["timeout"] == 30.0
        assert client_cls.call_args.kwargs["max_retries"] == 2


def test_startup_validation_rejects_mismatched_embedding_dimensions() -> None:
    with patch(
        "src.core.startup_checks.settings.OPENAI_EMBEDDING_DIMENSIONS",
        ChunkEntity.EMBEDDING_DIMENSIONS + 1,
    ), pytest.raises(RuntimeError, match="OPENAI_EMBEDDING_DIMENSIONS"):
        validate_startup_settings()


def test_startup_validation_requires_openai_key_when_not_debug() -> None:
    with (
        patch("src.core.startup_checks.settings.DEBUG", False),
        patch("src.core.startup_checks.settings.OPENAI_API_KEY", ""),
        pytest.raises(RuntimeError, match="OPENAI_API_KEY"),
    ):
        validate_startup_settings()


def test_startup_validation_rejects_unknown_file_storage_type() -> None:
    with (
        patch("src.core.startup_checks.settings.DEBUG", True),
        patch("src.core.startup_checks.settings.FILE_STORAGE_TYPE", "ftp"),
        pytest.raises(RuntimeError, match="FILE_STORAGE_TYPE"),
    ):
        validate_startup_settings()


def test_startup_validation_requires_bucket_for_s3_storage() -> None:
    with (
        patch("src.core.startup_checks.settings.DEBUG", True),
        patch("src.core.startup_checks.settings.FILE_STORAGE_TYPE", "s3"),
        patch("src.core.startup_checks.settings.AWS_S3_BUCKET", ""),
        pytest.raises(RuntimeError, match="AWS_S3_BUCKET"),
    ):
        validate_startup_settings()
