"""Tests for worker error handling and classification."""

from openai import APIConnectionError, APITimeoutError, RateLimitError
from requests.exceptions import ConnectionError, Timeout  # type: ignore[import-untyped,unused-ignore]

from src.kit.exceptions import DomainException, ValidationException
from src.worker.error_handling import classify_error


def _make_exception(exc_type: type[Exception]) -> Exception:
    return exc_type.__new__(exc_type)


class TestErrorClassification:
    """Test error classification for worker retry logic."""

    def test_rate_limit_error_is_retryable(self) -> None:
        """RateLimitError should be retryable."""
        exc = _make_exception(RateLimitError)
        is_retryable, reason = classify_error(exc)
        assert is_retryable is True
        assert reason == "api_error"

    def test_api_connection_error_is_retryable(self) -> None:
        """APIConnectionError should be retryable."""
        exc = _make_exception(APIConnectionError)
        is_retryable, reason = classify_error(exc)
        assert is_retryable is True
        assert reason == "api_error"

    def test_api_timeout_error_is_retryable(self) -> None:
        """APITimeoutError should be retryable."""
        exc = _make_exception(APITimeoutError)
        is_retryable, reason = classify_error(exc)
        assert is_retryable is True
        assert reason == "api_error"

    def test_timeout_error_is_retryable(self) -> None:
        """Timeout should be retryable."""
        exc = Timeout("timeout")
        is_retryable, reason = classify_error(exc)
        assert is_retryable is True
        assert reason == "timeout"

    def test_connection_error_is_retryable(self) -> None:
        """ConnectionError should be retryable."""
        exc = ConnectionError("connection refused")
        is_retryable, reason = classify_error(exc)
        assert is_retryable is True
        assert reason == "connection_error"

    def test_domain_exception_is_permanent(self) -> None:
        """DomainException should not be retryable."""

        class TestDomainException(DomainException):
            pass

        exc = TestDomainException("domain error")
        is_retryable, reason = classify_error(exc)
        assert is_retryable is False
        assert reason == "domain_error"

    def test_validation_exception_is_permanent(self) -> None:
        """ValidationException should not be retryable."""
        exc = ValidationException("invalid value")
        is_retryable, reason = classify_error(exc)
        assert is_retryable is False
        assert reason == "domain_error"

    def test_key_error_is_permanent(self) -> None:
        """KeyError should not be retryable."""
        exc = KeyError("missing key")
        is_retryable, reason = classify_error(exc)
        assert is_retryable is False
        assert reason == "code_error"

    def test_attribute_error_is_permanent(self) -> None:
        """AttributeError should not be retryable."""
        exc = AttributeError("missing attribute")
        is_retryable, reason = classify_error(exc)
        assert is_retryable is False
        assert reason == "code_error"

    def test_unknown_error_is_permanent(self) -> None:
        """Unknown errors should not be retryable by default."""
        exc = RuntimeError("unknown error")
        is_retryable, reason = classify_error(exc)
        assert is_retryable is False
        assert reason == "unknown_error"
