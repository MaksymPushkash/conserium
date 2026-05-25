from uuid import UUID

from src.application.dtos.knowledge_gap_dtos import KnowledgeGapAreaDTO
from src.application.dtos.learning_goal_dtos import (
    CreateLearningGoalDTO,
    LearningGoalDTO,
    RankedLearningResourceDTO,
    SuggestedLearningResourceDTO,
    UpdateLearningGoalDTO,
)
from src.presentation.schemas.knowledge_gap import KnowledgeGapAreaResponse
from src.presentation.schemas.learning_goal import (
    LearningGoalRequest,
    LearningGoalResponse,
    LearningGoalUpdateRequest,
    RankedLearningResourceResponse,
    SuggestedLearningResourceResponse,
)


def to_create_learning_goal_dto(body: LearningGoalRequest, user_id: UUID) -> CreateLearningGoalDTO:
    return CreateLearningGoalDTO(
        user_id=user_id,
        topic=body.topic,
        description=body.description,
        target_date=body.target_date,
    )


def to_update_learning_goal_dto(goal_id: UUID, body: LearningGoalUpdateRequest, user_id: UUID) -> UpdateLearningGoalDTO:
    return UpdateLearningGoalDTO(
        user_id=user_id,
        goal_id=goal_id,
        topic=body.topic,
        description=body.description,
        target_date=body.target_date,
        status=body.status,
    )


def to_learning_goal_response(dto: LearningGoalDTO) -> LearningGoalResponse:
    return LearningGoalResponse(
        id=dto.id,
        user_id=dto.user_id,
        topic=dto.topic,
        description=dto.description,
        target_date=dto.target_date,
        status=dto.status,
        progress_ratio=dto.progress_ratio,
        covered_count=dto.covered_count,
        missing_count=dto.missing_count,
        gaps=[to_gap_area_response(area) for area in dto.gaps],
        recommended_next_areas=dto.recommended_next_areas,
        suggested_resources=[to_suggested_resource_response(resource) for resource in dto.suggested_resources],
        deadline_status=dto.deadline_status,
        days_remaining=dto.days_remaining,
        created_at=dto.created_at,
        updated_at=dto.updated_at,
    )


def to_gap_area_response(dto: KnowledgeGapAreaDTO) -> KnowledgeGapAreaResponse:
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


def to_suggested_resource_response(dto: SuggestedLearningResourceDTO) -> SuggestedLearningResourceResponse:
    return SuggestedLearningResourceResponse(
        area=dto.area,
        title=dto.title,
        search_query=dto.search_query,
        reason=dto.reason,
        url=dto.url,
    )


def to_ranked_resource_response(dto: RankedLearningResourceDTO) -> RankedLearningResourceResponse:
    return RankedLearningResourceResponse(
        area=dto.area,
        title=dto.title,
        search_query=dto.search_query,
        reason=dto.reason,
        url=dto.url,
        excerpt=dto.excerpt,
        score=dto.score,
        warning=dto.warning,
        cached=dto.cached,
        refreshed_at=dto.refreshed_at,
    )
