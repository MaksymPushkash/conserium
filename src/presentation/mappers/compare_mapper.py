from uuid import UUID

from src.application.dtos.compare_dtos import CompareDocumentsDTO, CompareResultDTO
from src.presentation.mappers.query_mapper import to_query_source_response
from src.presentation.schemas.compare import CompareDocumentsRequest, CompareDocumentsResponse


def to_compare_documents_dto(body: CompareDocumentsRequest, user_id: UUID) -> CompareDocumentsDTO:
    return CompareDocumentsDTO(
        user_id=user_id,
        left_document_id=body.left_document_id,
        right_document_id=body.right_document_id,
        prompt=body.prompt,
        limit=body.limit,
    )


def to_compare_documents_response(dto: CompareResultDTO) -> CompareDocumentsResponse:
    return CompareDocumentsResponse(
        left_document_id=dto.left_document_id,
        right_document_id=dto.right_document_id,
        left_title=dto.left_title,
        right_title=dto.right_title,
        markdown=dto.markdown,
        sources=[to_query_source_response(source, index) for index, source in enumerate(dto.sources, start=1)],
    )
