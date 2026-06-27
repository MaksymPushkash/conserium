from uuid import UUID

from fastapi import Depends, Header, Query, status

from src.collections.schemas import CollectionListResponse
from src.collections.service import CollectionService, collections
from src.documents.ingestion import (
    ExternalIntakeService,
    ExternalItemIngester,
)
from src.documents.ingestion_dependencies import get_external_intake_service, get_external_item_ingester
from src.integrations.dependencies import get_api_key_authenticator
from src.integrations.service import ApiKeyAuthenticator
from src.postgres import AsyncReadSession, get_db_read_session
from src.public_api.schemas import PublicIngestRequest, PublicIngestResponse
from src.query.dependencies import get_query_executor
from src.query.schemas import QueryInput, QueryRequest, QueryResponse
from src.query.service import QueryExecutor, to_query_response
from src.routing import APIRouter
from src.webhooks.endpoints import to_external_ingest_response, to_external_intake_item_response
from src.webhooks.schemas import ExternalIngestResponse, ExternalIntakeListResponse

router = APIRouter(prefix="/public-api", tags=["public-api"])


def get_collection_service() -> CollectionService:
    return collections


@router.post("/ingest", response_model=PublicIngestResponse, status_code=status.HTTP_202_ACCEPTED)
async def public_ingest(
    body: PublicIngestRequest,
    authorization: str = Header(...),
    authenticate_api_key: ApiKeyAuthenticator = Depends(get_api_key_authenticator),
    ingest_external_item: ExternalItemIngester = Depends(get_external_item_ingester),
) -> PublicIngestResponse:
    principal = await authenticate_api_key(authorization, required_scope="ingest:write")
    result = await ingest_external_item(
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
    response = to_external_ingest_response(result)
    return PublicIngestResponse(intake_item=response.intake_item, document=response.document)


@router.get("/intake", response_model=ExternalIntakeListResponse)
async def list_public_intake_items(
    authorization: str = Header(...),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    authenticate_api_key: ApiKeyAuthenticator = Depends(get_api_key_authenticator),
    intake_service: ExternalIntakeService = Depends(get_external_intake_service),
) -> ExternalIntakeListResponse:
    principal = await authenticate_api_key(authorization, required_scope="status:read")
    items = await intake_service.list(user_id=principal.user_id, limit=limit, offset=offset)
    return ExternalIntakeListResponse(
        items=[to_external_intake_item_response(item) for item in items],
        limit=limit,
        offset=offset,
    )


@router.get("/intake/{intake_item_id}", response_model=ExternalIngestResponse)
async def get_public_intake_item(
    intake_item_id: UUID,
    authorization: str = Header(...),
    authenticate_api_key: ApiKeyAuthenticator = Depends(get_api_key_authenticator),
    intake_service: ExternalIntakeService = Depends(get_external_intake_service),
) -> ExternalIngestResponse:
    principal = await authenticate_api_key(authorization, required_scope="status:read")
    result = await intake_service.get(user_id=principal.user_id, intake_item_id=intake_item_id)
    return to_external_ingest_response(result)


@router.post("/intake/{intake_item_id}/retry", response_model=ExternalIngestResponse, status_code=status.HTTP_202_ACCEPTED)
async def retry_public_intake_item(
    intake_item_id: UUID,
    authorization: str = Header(...),
    authenticate_api_key: ApiKeyAuthenticator = Depends(get_api_key_authenticator),
    intake_service: ExternalIntakeService = Depends(get_external_intake_service),
) -> ExternalIngestResponse:
    principal = await authenticate_api_key(authorization, required_scope="ingest:write")
    result = await intake_service.retry(user_id=principal.user_id, intake_item_id=intake_item_id)
    return to_external_ingest_response(result)


@router.get("/collections", response_model=CollectionListResponse)
async def list_public_collections(
    authorization: str = Header(...),
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    authenticate_api_key: ApiKeyAuthenticator = Depends(get_api_key_authenticator),
    session: AsyncReadSession = Depends(get_db_read_session),
    collection_service: CollectionService = Depends(get_collection_service),
) -> CollectionListResponse:
    principal = await authenticate_api_key(authorization, required_scope="collections:read")
    return await collection_service.list(
        session,
        user_id=principal.user_id,
        limit=limit,
        offset=offset,
        workspace_id=None,
    )


@router.post("/query", response_model=QueryResponse)
async def public_query(
    body: QueryRequest,
    authorization: str = Header(...),
    authenticate_api_key: ApiKeyAuthenticator = Depends(get_api_key_authenticator),
    query_executor: QueryExecutor = Depends(get_query_executor),
) -> QueryResponse:
    principal = await authenticate_api_key(authorization, required_scope="query:write")
    result = await query_executor(
        QueryInput(
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


__all__ = ["router"]
