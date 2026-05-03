from unittest.mock import patch

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
