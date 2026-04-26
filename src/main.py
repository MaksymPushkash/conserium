from contextlib import asynccontextmanager

from dishka.integrations.fastapi import setup_dishka
from fastapi import FastAPI

from src.core.container import container
from src.presentation.api.v1.auth import router as auth_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await container.close()



def create_app() -> FastAPI:
    app = FastAPI(lifespan=lifespan)
    setup_dishka(container, app)
    
    app.include_router(auth_router, prefix="/api/v1")

    @app.get("/", tags=["health"])
    async def health_check() -> dict[str, str]:
        return {"status": "OK"}


    return app

app = create_app()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
    