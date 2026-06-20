import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api import router as api_router
from src.exceptions import setup_exception_handlers
from src.lifecycle import dispose_dependencies
from src.observability.health import router as health_router
from src.observability.logging import configure_logging
from src.observability.rate_limit import setup_rate_limiting
from src.postgres import dispose_engine
from src.settings import settings
from src.startup_checks import validate_startup_settings
from src.worker import declare_configured_queues

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    configure_logging(debug=settings.DEBUG)
    validate_startup_settings()
    try:
        declare_configured_queues()
    except Exception:
        logger.warning("celery_queue_declaration_failed", exc_info=True)
    yield
    await dispose_dependencies()
    await dispose_engine()


def create_app() -> FastAPI:
    app = FastAPI(lifespan=lifespan, title="conserium")
    setup_rate_limiting(app)
    setup_exception_handlers(app)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins(),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health_router)
    app.include_router(api_router)

    return app


def _cors_origins() -> list[str]:
    origins = {settings.FRONTEND_URL}
    if settings.DEBUG:
        origins.update({"http://localhost:3000", "http://127.0.0.1:3000"})
    return sorted(origin for origin in origins if origin)


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
