from collections.abc import AsyncIterator
from time import perf_counter

from dishka.integrations.fastapi import FromDishka, inject
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from src.application.use_cases.query.query_use_case import QueryUseCase
from src.application.use_cases.query.stream_query_use_case import StreamQueryUseCase
from src.core.metrics import metrics_registry
from src.presentation.dependencies.auth import CurrentUser
from src.presentation.mappers.query_mapper import to_query_response
from src.presentation.mappers.query_request_mapper import to_query_dto
from src.presentation.middleware.rate_limit import limiter
from src.presentation.schemas.query import QueryRequest, QueryResponse
from src.presentation.sse import format_sse_event

router = APIRouter(prefix="/query", tags=["query"])


@router.post("", response_model=QueryResponse)
@limiter.limit("100/minute")
@inject
async def query_documents(
    request: Request,
    body: QueryRequest,
    current_user: CurrentUser,
    use_case: FromDishka[QueryUseCase],
) -> QueryResponse:
    with metrics_registry.timer(
        "cortex_query_latency_seconds",
        "Latency of query execution in seconds.",
        labels={"mode": "sync"},
    ):
        result = await use_case(to_query_dto(body, current_user.id))
    metrics_registry.inc_counter(
        "cortex_http_requests_total",
        "HTTP requests handled by selected endpoints.",
        labels={"endpoint": "query_documents", "method": "POST", "status": "200"},
    )
    return to_query_response(result)


@router.post("/stream")
@limiter.limit("100/minute")
@inject
async def stream_query_documents(
    request: Request,
    body: QueryRequest,
    current_user: CurrentUser,
    use_case: FromDishka[StreamQueryUseCase],
) -> StreamingResponse:
    async def event_stream() -> AsyncIterator[str]:
        started_at = perf_counter()
        try:
            async for event in use_case(to_query_dto(body, current_user.id)):
                yield format_sse_event(event)
        finally:
            metrics_registry.observe_histogram(
                "cortex_query_latency_seconds",
                "Latency of query execution in seconds.",
                labels={"mode": "stream"},
                value=perf_counter() - started_at,
            )
            metrics_registry.inc_counter(
                "cortex_http_requests_total",
                "HTTP requests handled by selected endpoints.",
                labels={"endpoint": "stream_query_documents", "method": "POST", "status": "200"},
            )

    return StreamingResponse(event_stream(), media_type="text/event-stream")
