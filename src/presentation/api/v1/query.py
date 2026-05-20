from collections.abc import AsyncIterator
from time import perf_counter

from dishka.integrations.fastapi import FromDishka, inject
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from src.application.use_cases.query.query_use_case import QueryUseCase
from src.application.use_cases.query.stream_query_use_case import StreamQueryUseCase
from src.presentation.api.metrics import observe_query_latency, query_latency_timer, record_http_request
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
    with query_latency_timer("sync"):
        result = await use_case(to_query_dto(body, current_user))
    record_http_request("query_documents", status="200")
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
            async for event in use_case(to_query_dto(body, current_user)):
                yield format_sse_event(event)
        finally:
            observe_query_latency("stream", perf_counter() - started_at)
            record_http_request("stream_query_documents", status="200")

    return StreamingResponse(event_stream(), media_type="text/event-stream")
