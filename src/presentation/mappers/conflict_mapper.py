from src.application.dtos.conflict_dtos import ConflictDetectionResultDTO, ConflictDocumentDTO, ConflictFindingDTO
from src.presentation.schemas.conflict import (
    ConflictDetectionResponse,
    ConflictDocumentResponse,
    ConflictFindingResponse,
)


def to_conflict_detection_response(dto: ConflictDetectionResultDTO) -> ConflictDetectionResponse:
    return ConflictDetectionResponse(
        collection_id=dto.collection_id,
        analyzed_document_count=dto.analyzed_document_count,
        conflicts=[to_conflict_finding_response(conflict) for conflict in dto.conflicts],
    )


def to_conflict_finding_response(dto: ConflictFindingDTO) -> ConflictFindingResponse:
    return ConflictFindingResponse(
        subject=dto.subject,
        summary=dto.summary,
        documents=[to_conflict_document_response(document) for document in dto.documents],
        evidence=dto.evidence,
        score=dto.score,
    )


def to_conflict_document_response(dto: ConflictDocumentDTO) -> ConflictDocumentResponse:
    return ConflictDocumentResponse(id=dto.id, title=dto.title)
