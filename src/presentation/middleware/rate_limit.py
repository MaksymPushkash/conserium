"""Rate limiting middleware for production protection."""

import structlog
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

logger = structlog.get_logger(__name__)

limiter = Limiter(key_func=get_remote_address, default_limits=["100/minute"])


async def rate_limit_exceeded_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handle rate limit exceeded errors."""
    logger.warning(
        "rate_limit_exceeded",
        client=request.client.host if request.client else "unknown",
        path=request.url.path,
        method=request.method,
    )
    return JSONResponse(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        content={
            "detail": "Too many requests. Please try again later.",
            "retry_after": 60,
        },
    )


def setup_rate_limiting(app: FastAPI) -> None:
    """Configure rate limiting on FastAPI app."""
    limiter.reset()
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)
