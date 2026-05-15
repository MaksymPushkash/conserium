import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from dishka.integrations.fastapi import setup_dishka
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.core.config import settings
from src.core.container import container
from src.core.logging import configure_logging
from src.core.startup_checks import validate_startup_settings
from src.infrastructure.celery.app import declare_configured_queues
from src.presentation.api.health import router as health_router
from src.presentation.api.v1.auth import router as auth_router
from src.presentation.api.v1.chats import router as chat_router
from src.presentation.api.v1.collections import router as collection_router
from src.presentation.api.v1.documents import router as document_router
from src.presentation.api.v1.ingestion import router as ingestion_router
from src.presentation.api.v1.notes import router as note_router
from src.presentation.api.v1.observability import router as observability_router
from src.presentation.api.v1.query import router as query_router
from src.presentation.api.v1.user import router as user_router
from src.presentation.exception_handlers import setup_exception_handlers
from src.presentation.middleware.rate_limit import setup_rate_limiting

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
    await container.close()


def create_app() -> FastAPI:
    app = FastAPI(lifespan=lifespan, title="cortex")
    setup_dishka(container, app)
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
    app.include_router(auth_router, prefix="/api/v1")
    app.include_router(user_router, prefix="/api/v1")
    app.include_router(collection_router, prefix="/api/v1")
    app.include_router(document_router, prefix="/api/v1")
    app.include_router(ingestion_router, prefix="/api/v1")
    app.include_router(note_router, prefix="/api/v1")
    app.include_router(chat_router, prefix="/api/v1")
    app.include_router(query_router, prefix="/api/v1")
    app.include_router(observability_router, prefix="/api/v1")

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
