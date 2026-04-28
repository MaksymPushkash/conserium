from contextlib import asynccontextmanager

from dishka.integrations.fastapi import setup_dishka
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from src.core.config import settings
from src.core.container import container
from src.core.logging import configure_logging
from src.domain.exceptions import (
    EmailAlreadyExistsException,
    InvalidCredentialsException,
    InvalidEmailException,
    InvalidPasswordException,
    InvalidTokenException,
    UserAlreadyInactiveException,
    UserInactiveException,
)
from src.presentation.api.v1.auth import router as auth_router
from src.presentation.api.v1.user import router as user_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging(debug=settings.DEBUG)
    yield
    await container.close()



def create_app() -> FastAPI:
    app = FastAPI(lifespan=lifespan, title="cortex")
    setup_dishka(container, app)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.FRONTEND_URL],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    _DOMAIN_EXCEPTION_MAP: dict[type[Exception], tuple[int, str | None]] = {
        EmailAlreadyExistsException: (status.HTTP_409_CONFLICT, None),
        InvalidCredentialsException: (status.HTTP_401_UNAUTHORIZED, None),
        InvalidTokenException: (status.HTTP_401_UNAUTHORIZED, None),
        UserInactiveException: (status.HTTP_403_FORBIDDEN, None),
        UserAlreadyInactiveException: (status.HTTP_409_CONFLICT, None),
        InvalidEmailException: (status.HTTP_422_UNPROCESSABLE_ENTITY, None),
        InvalidPasswordException: (status.HTTP_422_UNPROCESSABLE_ENTITY, None),
    }

    for exc_cls, (status_code, _) in _DOMAIN_EXCEPTION_MAP.items():
        def _handler_factory(sc: int):
            async def handler(request: Request, exc: Exception) -> JSONResponse:
                return JSONResponse(status_code=sc, content={"detail": str(exc)})
            return handler
        app.add_exception_handler(exc_cls, _handler_factory(status_code))

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": "Internal server error"},
        )

    app.include_router(auth_router, prefix="/api/v1")
    app.include_router(user_router, prefix="/api/v1")

    @app.get("/", tags=["health"])
    async def health_check() -> dict[str, str]:
        return {"status": "OK"}


    return app

app = create_app()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)