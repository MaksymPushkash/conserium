from uuid import UUID

from dishka.integrations.fastapi import FromDishka, inject
from fastapi import APIRouter, Header, Query, status

from src.application.dtos.collection_dtos import ListCollectionsDTO
from src.application.dtos.external_intake_dtos import ExternalIngestDTO
from src.application.dtos.query_dtos import QueryDTO
from src.application.use_cases.api_keys import AuthenticateApiKeyUseCase
from src.application.use_cases.documents.collection_use_cases import ListCollectionsUseCase
from src.application.use_cases.external_intake import (
    GetExternalIntakeItemUseCase,
    IngestExternalItemUseCase,
    ListExternalIntakeItemsUseCase,
    RetryExternalIntakeItemUseCase,
)
from src.application.use_cases.query.query_use_case import QueryUseCase
from src.presentation.mappers.collection_mapper import to_collection_list_response
from src.presentation.mappers.external_intake_mapper import (
    to_external_ingest_response,
    to_external_intake_item_response,
)
from src.presentation.mappers.query_mapper import to_query_response
from src.presentation.schemas.collection import CollectionListResponse
from src.presentation.schemas.external_intake import ExternalIngestResponse, ExternalIntakeListResponse
from src.presentation.schemas.public_api import PublicIngestRequest, PublicIngestResponse
from src.presentation.schemas.query import QueryRequest, QueryResponse

router = APIRouter(prefix="/public-api", tags=["public-api"])


@router.post("/ingest", response_model=PublicIngestResponse, status_code=status.HTTP_202_ACCEPTED)
@inject
async def public_ingest(
    body: PublicIngestRequest,
    authenticate_api_key: FromDishka[AuthenticateApiKeyUseCase],
    ingest_external_item: FromDishka[IngestExternalItemUseCase],
    authorization: str = Header(...),
) -> PublicIngestResponse:
    principal = await authenticate_api_key(authorization, required_scope="ingest:write")
    result = await ingest_external_item(
        ExternalIngestDTO(
            user_id=principal.user_id,
            api_key_id=principal.api_key_id,
            provider=body.provider or "public-api",
            title=body.title,
            type=body.type,
            collection_id=body.collection_id,
            tags=body.tags,
            source_url=body.source_url,
            raw_content=body.raw_content,
            language=body.language,
            external_id=body.external_id,
            idempotency_key=body.idempotency_key,
            payload_metadata=body.metadata,
        )
    )
    response = to_external_ingest_response(result)
    return PublicIngestResponse(intake_item=response.intake_item, document=response.document)


@router.get("/intake", response_model=ExternalIntakeListResponse)
@inject
async def list_public_intake_items(
    authenticate_api_key: FromDishka[AuthenticateApiKeyUseCase],
    list_intake_items: FromDishka[ListExternalIntakeItemsUseCase],
    authorization: str = Header(...),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> ExternalIntakeListResponse:
    principal = await authenticate_api_key(authorization, required_scope="status:read")
    items = await list_intake_items(user_id=principal.user_id, limit=limit, offset=offset)
    return ExternalIntakeListResponse(
        items=[to_external_intake_item_response(item) for item in items],
        limit=limit,
        offset=offset,
    )


@router.get("/intake/{intake_item_id}", response_model=ExternalIngestResponse)
@inject
async def get_public_intake_item(
    intake_item_id: UUID,
    authenticate_api_key: FromDishka[AuthenticateApiKeyUseCase],
    get_intake_item: FromDishka[GetExternalIntakeItemUseCase],
    authorization: str = Header(...),
) -> ExternalIngestResponse:
    principal = await authenticate_api_key(authorization, required_scope="status:read")
    result = await get_intake_item(user_id=principal.user_id, intake_item_id=intake_item_id)
    return to_external_ingest_response(result)


@router.post("/intake/{intake_item_id}/retry", response_model=ExternalIngestResponse, status_code=status.HTTP_202_ACCEPTED)
@inject
async def retry_public_intake_item(
    intake_item_id: UUID,
    authenticate_api_key: FromDishka[AuthenticateApiKeyUseCase],
    retry_intake_item: FromDishka[RetryExternalIntakeItemUseCase],
    authorization: str = Header(...),
) -> ExternalIngestResponse:
    principal = await authenticate_api_key(authorization, required_scope="ingest:write")
    result = await retry_intake_item(user_id=principal.user_id, intake_item_id=intake_item_id)
    return to_external_ingest_response(result)


@router.get("/collections", response_model=CollectionListResponse)
@inject
async def list_public_collections(
    authenticate_api_key: FromDishka[AuthenticateApiKeyUseCase],
    list_collections: FromDishka[ListCollectionsUseCase],
    authorization: str = Header(...),
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> CollectionListResponse:
    principal = await authenticate_api_key(authorization, required_scope="collections:read")
    result = await list_collections(ListCollectionsDTO(user_id=principal.user_id, limit=limit, offset=offset))
    return to_collection_list_response(result)


@router.post("/query", response_model=QueryResponse)
@inject
async def public_query(
    body: QueryRequest,
    authenticate_api_key: FromDishka[AuthenticateApiKeyUseCase],
    query_use_case: FromDishka[QueryUseCase],
    authorization: str = Header(...),
) -> QueryResponse:
    principal = await authenticate_api_key(authorization, required_scope="query:write")
    result = await query_use_case(
        QueryDTO(
            user_id=principal.user_id,
            query=body.query,
            conversation_id=body.conversation_id,
            collection_id=body.collection_id,
            tag_names=tuple(tag.strip().lower() for tag in body.tag_names or [] if tag.strip()) or None,
            document_types=tuple(body.document_types) if body.document_types else None,
            document_ids=(body.document_id,) if body.document_id else None,
            limit=body.limit,
        )
    )
    return to_query_response(result)
