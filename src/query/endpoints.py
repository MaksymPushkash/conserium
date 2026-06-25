from collections.abc import AsyncIterator
from time import perf_counter

from fastapi import Depends, Request
from fastapi.responses import StreamingResponse

from src.auth.auth import CurrentUser
from src.observability.metrics import observe_query_latency, query_latency_timer, record_http_request
from src.observability.rate_limit import limiter
from src.query.dependencies import get_query_executor, get_stream_query_executor
from src.query.schemas import QueryRequest, QueryResponse
from src.query.service import (
    QueryExecutor,
    StreamQueryExecutor,
    build_query_payload,
    format_sse_event,
    to_query_response,
)
from src.routing import APIRouter

router = APIRouter(prefix="/query", tags=["query"])


@router.post("", response_model=QueryResponse)
@limiter.limit("100/minute")
async def query_documents(
    request: Request,
    body: QueryRequest,
    current_user: CurrentUser,
    handler: QueryExecutor = Depends(get_query_executor),
) -> QueryResponse:
    with query_latency_timer("sync"):
        result = await handler(build_query_payload(body, current_user))
    record_http_request("query_documents", status="200")
    return to_query_response(result)


@router.post("/stream")
@limiter.limit("100/minute")
async def stream_query_documents(
    request: Request,
    body: QueryRequest,
    current_user: CurrentUser,
    handler: StreamQueryExecutor = Depends(get_stream_query_executor),
) -> StreamingResponse:
    async def event_stream() -> AsyncIterator[str]:
        started_at = perf_counter()
        try:
            async for event in handler(build_query_payload(body, current_user)):
                yield format_sse_event(event)
        finally:
            observe_query_latency("stream", perf_counter() - started_at)
            record_http_request("stream_query_documents", status="200")

    return StreamingResponse(event_stream(), media_type="text/event-stream")


__all__ = ["router"]
