from src.application.dtos.knowledge_gap_dtos import KnowledgeGapAreaDTO, KnowledgeGapDTO
from src.presentation.schemas.knowledge_gap import KnowledgeGapAreaResponse, KnowledgeGapResponse


def to_knowledge_gap_response(dto: KnowledgeGapDTO) -> KnowledgeGapResponse:
    return KnowledgeGapResponse(
        topic=dto.topic,
        covered_count=dto.covered_count,
        missing_count=dto.missing_count,
        coverage_ratio=dto.coverage_ratio,
        areas=[to_knowledge_gap_area_response(area) for area in dto.areas],
    )


def to_knowledge_gap_area_response(dto: KnowledgeGapAreaDTO) -> KnowledgeGapAreaResponse:
    return KnowledgeGapAreaResponse(
        name=dto.name,
        covered=dto.covered,
        evidence_count=dto.evidence_count,
        evidence_titles=dto.evidence_titles,
    )
