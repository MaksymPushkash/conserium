from fastapi import APIRouter
from fastapi.responses import PlainTextResponse

from src.core.metrics import metrics_registry

router = APIRouter(tags=["health"])


def health_payload() -> dict[str, str]:
    return {"status": "OK"}


@router.get("/")
async def health_check() -> dict[str, str]:
    return health_payload()


@router.get("/health", include_in_schema=False)
async def health_check_alias() -> dict[str, str]:
    return health_payload()


@router.get("/metrics", include_in_schema=False)
async def metrics() -> PlainTextResponse:
    return PlainTextResponse(metrics_registry.render_prometheus(), media_type="text/plain; version=0.0.4")
