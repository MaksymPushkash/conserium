"""Integration tests for database configuration."""

import pytest
from sqlalchemy.ext.asyncio import create_async_engine

from src.core.config import settings


class TestDatabaseConfiguration:
    """Test database configuration including timeouts."""

    def test_connect_timeout_configured(self) -> None:
        """Verify connect timeout is configured."""
        assert settings.DB_CONNECT_TIMEOUT > 0
        assert settings.DB_CONNECT_TIMEOUT <= 30  # Reasonable limit

    def test_query_timeout_configured(self) -> None:
        """Verify query timeout is configured."""
        assert settings.DB_QUERY_TIMEOUT > 0
        assert settings.DB_QUERY_TIMEOUT <= 60  # Reasonable limit

    def test_connect_timeout_less_than_query_timeout(self) -> None:
        """Connect timeout should be less than query timeout."""
        assert settings.DB_CONNECT_TIMEOUT < settings.DB_QUERY_TIMEOUT

    @pytest.mark.asyncio
    async def test_engine_created_with_timeouts(self) -> None:
        """Verify engine can be created with timeout configuration."""
        # This test verifies the configuration doesn't break engine creation
        engine = create_async_engine(
            settings.DATABASE_URL,
            pool_size=5,
            max_overflow=2,
            pool_pre_ping=True,
            pool_recycle=300,
            connect_args={
                "timeout": settings.DB_CONNECT_TIMEOUT,
                "command_timeout": settings.DB_QUERY_TIMEOUT,
            },
        )
        # Clean up
        await engine.dispose()
        # If we got here without exception, configuration is valid
        assert True

    def test_database_pool_size_configured(self) -> None:
        """Verify database pool is configured."""
        assert settings.DATABASE_POOL_SIZE > 0
        assert settings.DATABASE_POOL_SIZE <= 50  # Reasonable limit

    def test_database_max_overflow_configured(self) -> None:
        """Verify max overflow is configured."""
        assert settings.DATABASE_MAX_OVERFLOW >= 0
        assert settings.DATABASE_MAX_OVERFLOW <= 30  # Reasonable limit
