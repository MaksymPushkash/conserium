from dishka.integrations.fastapi import FromDishka, inject
from fastapi import APIRouter, Header, status

from src.application.dtos.external_intake_dtos import ExternalIngestDTO
from src.application.use_cases.api_keys import AuthenticateApiKeyUseCase
from src.application.use_cases.external_intake import IngestExternalItemUseCase
from src.presentation.mappers.external_intake_mapper import to_external_ingest_response
from src.presentation.schemas.public_api import PublicIngestRequest, PublicIngestResponse

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
