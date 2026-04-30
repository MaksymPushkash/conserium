from collections.abc import AsyncIterator

from dishka.integrations.fastapi import FromDishka, inject
from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from src.application.dtos.query_dtos import QueryDTO
from src.application.use_cases.query.query_use_case import QueryUseCase
from src.application.use_cases.query.stream_query_use_case import StreamQueryUseCase
from src.presentation.dependencies.auth import CurrentUser
from src.presentation.schemas.query import QueryRequest, QueryResponse
from src.presentation.sse import format_sse_event

router = APIRouter(prefix="/query", tags=["query"])


@router.post("", response_model=QueryResponse)
@inject
async def query_documents(
    body: QueryRequest,
    current_user: CurrentUser,
    use_case: FromDishka[QueryUseCase],
) -> QueryResponse:
    result = await use_case(
        QueryDTO(
            user_id=current_user.id,
            query=body.query,
            conversation_id=body.conversation_id,
            collection_id=body.collection_id,
            limit=body.limit,
        )
    )
    return QueryResponse.from_dto(result)


@router.post("/stream")
@inject
async def stream_query_documents(
    body: QueryRequest,
    current_user: CurrentUser,
    use_case: FromDishka[StreamQueryUseCase],
) -> StreamingResponse:
    async def event_stream() -> AsyncIterator[str]:
        async for event in use_case(
            QueryDTO(
                user_id=current_user.id,
                query=body.query,
                conversation_id=body.conversation_id,
                collection_id=body.collection_id,
                limit=body.limit,
            )
        ):
            yield format_sse_event(event)

    return StreamingResponse(event_stream(), media_type="text/event-stream")
