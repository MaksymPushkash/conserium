from src.application.dtos.external_intake_dtos import ExternalIngestResultDTO, ExternalIntakeItemDTO
from src.presentation.mappers.document_mapper import to_document_response
from src.presentation.schemas.external_intake import ExternalIngestResponse, ExternalIntakeItemResponse


def to_external_intake_item_response(dto: ExternalIntakeItemDTO) -> ExternalIntakeItemResponse:
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


def to_external_ingest_response(dto: ExternalIngestResultDTO) -> ExternalIngestResponse:
    return ExternalIngestResponse(
        intake_item=to_external_intake_item_response(dto.intake_item),
        document=to_document_response(dto.document) if dto.document is not None else None,
    )
