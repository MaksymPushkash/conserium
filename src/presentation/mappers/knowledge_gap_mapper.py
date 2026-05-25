from src.application.dtos.knowledge_gap_dtos import KnowledgeGapAreaDTO, KnowledgeGapDTO, KnowledgeGapListDTO
from src.presentation.schemas.knowledge_gap import (
    KnowledgeGapAreaResponse,
    KnowledgeGapListResponse,
    KnowledgeGapResponse,
)


def to_knowledge_gap_list_response(dto: KnowledgeGapListDTO) -> KnowledgeGapListResponse:
    return KnowledgeGapListResponse(
        items=[to_knowledge_gap_response(item) for item in dto.items],
        total=dto.total,
    )


def to_knowledge_gap_response(dto: KnowledgeGapDTO) -> KnowledgeGapResponse:
    return KnowledgeGapResponse(
        id=dto.id,
        topic=dto.topic,
        collection_id=str(dto.collection_id) if dto.collection_id else None,
        covered_count=dto.covered_count,
        missing_count=dto.missing_count,
        coverage_ratio=dto.coverage_ratio,
        why_detected=dto.why_detected,
        missing_source_types=dto.missing_source_types,
        severity=dto.severity,
        rationale=dto.rationale,
        suggested_actions=dto.suggested_actions,
        areas=[to_knowledge_gap_area_response(area) for area in dto.areas],
    )


def to_knowledge_gap_area_response(dto: KnowledgeGapAreaDTO) -> KnowledgeGapAreaResponse:
    return KnowledgeGapAreaResponse(
        id=dto.id,
        name=dto.name,
        covered=dto.covered,
        evidence_count=dto.evidence_count,
        evidence_titles=dto.evidence_titles,
        why_detected=dto.why_detected,
        missing_source_types=dto.missing_source_types,
        severity=dto.severity,
        rationale=dto.rationale,
        suggested_actions=dto.suggested_actions,
    )
