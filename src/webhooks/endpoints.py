from fastapi import Depends, Header, status

from src.documents.ingestion import ExternalItemIngester
from src.documents.ingestion_dependencies import get_external_item_ingester
from src.documents.schemas import (
    ExternalIngestResult,
    ExternalIntakeItem,
)
from src.documents.service import to_document_response
from src.integrations.api_keys import ApiKeyAuthenticator
from src.integrations.dependencies import get_api_key_authenticator
from src.routing import APIRouter
from src.webhooks.schemas import ExternalIngestRequest, ExternalIngestResponse, ExternalIntakeItemResponse

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@router.post("/ingest", response_model=ExternalIngestResponse, status_code=status.HTTP_202_ACCEPTED)
async def webhook_ingest(
    body: ExternalIngestRequest,
    authorization: str = Header(...),
    authenticate_api_key: ApiKeyAuthenticator = Depends(get_api_key_authenticator),
    ingest_external_item: ExternalItemIngester = Depends(get_external_item_ingester),
) -> ExternalIngestResponse:
    principal = await authenticate_api_key(authorization, required_scope="ingest:write")
    result = await ingest_external_item(
        user_id=principal.user_id,
        api_key_id=principal.api_key_id,
        provider=body.provider or "webhook",
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
    return to_external_ingest_response(result)


def to_external_intake_item_response(dto: ExternalIntakeItem) -> ExternalIntakeItemResponse:
    return ExternalIntakeItemResponse(
        id=dto.id,
        provider=dto.provider,
        external_id=dto.external_id,
        idempotency_key=dto.idempotency_key,
        title=dto.title,
        type=dto.type,
        collection_id=dto.collection_id,
        tags=dto.tags,
        source_url=dto.source_url,
        status=dto.status,
        error_reason=dto.error_reason,
        document_id=dto.document_id,
        payload_metadata=dto.payload_metadata,
        created_at=dto.created_at,
        updated_at=dto.updated_at,
    )


def to_external_ingest_response(dto: ExternalIngestResult) -> ExternalIngestResponse:
    return ExternalIngestResponse(
        intake_item=to_external_intake_item_response(dto.intake_item),
        document=to_document_response(dto.document) if dto.document is not None else None,
    )


__all__ = [
    "router",
    "to_external_ingest_response",
    "to_external_intake_item_response",
]
