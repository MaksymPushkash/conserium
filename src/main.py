from fastapi import FastAPI


def create_app() -> FastAPI:
    app = FastAPI()

    @app.get("/", tags=["health"])
    async def health_check() -> dict[str, str]:
        return {"status": "OK"}



    return app

app = create_app()
