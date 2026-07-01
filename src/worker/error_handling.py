from typing import Any

import structlog
from openai import APIConnectionError, APITimeoutError, RateLimitError
from requests.exceptions import ConnectionError, Timeout  # type: ignore[import-untyped,unused-ignore]

from src.kit.exceptions import DomainException

logger = structlog.get_logger(__name__)


class RetryableTaskError(Exception):
    pass


class RetryableError(Exception):
    """Errors that should trigger task retry."""

    pass


class PermanentError(Exception):
    """Errors that should not retry."""

    pass


def classify_error(exc: Exception) -> tuple[bool, str]:
    """Classify if error is retryable and get reason.

    Returns:
        (is_retryable, reason)
    """
    # Retryable: Transient API errors
    if isinstance(exc, (RateLimitError, APIConnectionError, APITimeoutError)):
        return True, "api_error"

    # Retryable: Network timeouts
    if isinstance(exc, Timeout):
        return True, "timeout"

    # Retryable: Connection errors
    if isinstance(exc, ConnectionError):
        return True, "connection_error"

    # Permanent: Domain/business logic and validation errors
    if isinstance(exc, DomainException):
        return False, "domain_error"

    # Permanent: Code bugs (missing keys, attributes)
    if isinstance(exc, (KeyError, AttributeError)):
        return False, "code_error"

    # Unknown: Don't retry by default
    return False, "unknown_error"


def handle_worker_error(
    exc: Exception,
    task_name: str,
    task_id: str,
    current_retries: int,
    max_retries: int,
    document_id: str | None = None,
) -> dict[str, Any]:
    """Handle worker task error and return result dict.

    Args:
        exc: The exception that occurred
        task_name: Name of the worker task
        task_id: Worker task ID
        current_retries: Current retry count
        max_retries: Maximum retry count
        document_id: Document ID if applicable

    Returns:
        Result dict with status FAILED
    """
    is_retryable, reason = classify_error(exc)

    log_context = {
        "task_name": task_name,
        "task_id": task_id,
        "error_type": type(exc).__name__,
        "error_reason": reason,
        "is_retryable": is_retryable,
        "retry_count": current_retries,
        "max_retries": max_retries,
        "error": str(exc),
    }
    if document_id:
        log_context["document_id"] = document_id

    logger.error("worker_task_error", **log_context)

    if is_retryable and current_retries < max_retries:
        countdown = min(2**current_retries * 60, 3600)
        logger.info("retrying_task", countdown=countdown, **log_context)
        return {"retry": True, "countdown": countdown}

    logger.error("worker_task_permanent_failure", reason=reason, **log_context)
    return {
        "status": "FAILED",
        "error": str(exc),
        "error_type": type(exc).__name__,
        "reason": reason,
        "document_id": document_id,
    }
