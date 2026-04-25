from fastapi import FastAPI


def create_app() -> FastAPI:
    app = FastAPI()

    @app.get("/", tags=["health"])
    async def health_check() -> dict[str, str]:
        return {"status": "OK"}



    return app

app = create_app()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
    