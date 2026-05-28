from dishka.integrations.fastapi import FromDishka, inject
from fastapi import APIRouter, Request

from src.application.use_cases.collection_shares import GetPublicCollectionUseCase, QueryPublicCollectionUseCase
from src.presentation.mappers.collection_share_mapper import to_public_collection_response
from src.presentation.mappers.query_mapper import to_query_response
from src.presentation.middleware.rate_limit import limiter
from src.presentation.schemas.collection_share import PublicCollectionResponse
from src.presentation.schemas.query import QueryRequest, QueryResponse

router = APIRouter(prefix="/public", tags=["public"])


@router.get("/collections/{slug}", response_model=PublicCollectionResponse)
@inject
async def get_public_collection(
    slug: str,
    use_case: FromDishka[GetPublicCollectionUseCase],
) -> PublicCollectionResponse:
    result = await use_case(slug=slug)
    return to_public_collection_response(result)


@router.post("/collections/{slug}/query", response_model=QueryResponse)
@limiter.limit("20/minute")
@inject
async def query_public_collection(
    request: Request,
    slug: str,
    body: QueryRequest,
    use_case: FromDishka[QueryPublicCollectionUseCase],
) -> QueryResponse:
    result = await use_case(slug=slug, query=body.query, limit=body.limit)
    return to_query_response(result)
