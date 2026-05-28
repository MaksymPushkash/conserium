from uuid import UUID

from src.application.dtos.compare_dtos import CompareDocumentsDTO, CompareListDTO, CompareResultDTO
from src.presentation.mappers.query_mapper import to_query_source_response
from src.presentation.schemas.compare import (
    CompareDocumentsRequest,
    CompareDocumentsResponse,
    CompareEvidenceRowResponse,
    CompareListResponse,
)


def to_compare_documents_dto(body: CompareDocumentsRequest, user_id: UUID) -> CompareDocumentsDTO:
    return CompareDocumentsDTO(
        user_id=user_id,
        left_document_id=body.left_document_id,
        right_document_id=body.right_document_id,
        prompt=body.prompt,
        dimensions=tuple(body.dimensions) if body.dimensions else None,
        limit=body.limit,
    )


def to_compare_documents_response(dto: CompareResultDTO) -> CompareDocumentsResponse:
    return CompareDocumentsResponse(
        id=dto.id,
        collection_id=dto.collection_id,
        left_document_id=dto.left_document_id,
        right_document_id=dto.right_document_id,
        left_title=dto.left_title,
        right_title=dto.right_title,
        dimensions=dto.dimensions,
        markdown=dto.markdown,
        summary=dto.summary,
        evidence_rows=[
            CompareEvidenceRowResponse(
                dimension=row.dimension,
                left_evidence=row.left_evidence,
                right_evidence=row.right_evidence,
                assessment=row.assessment,
                left_source_id=row.left_source_id,
                right_source_id=row.right_source_id,
                left_citation=row.left_citation,
                right_citation=row.right_citation,
                confidence=row.confidence,
                rationale=row.rationale,
            )
            for row in dto.evidence_rows
        ],
        sources=[to_query_source_response(source, index) for index, source in enumerate(dto.sources, start=1)],
        created_at=dto.created_at,
    )


def to_compare_list_response(dto: CompareListDTO) -> CompareListResponse:
    return CompareListResponse(
        items=[to_compare_documents_response(item) for item in dto.items],
        total=dto.total,
    )
