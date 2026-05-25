from uuid import UUID

from src.application.dtos.draft_dtos import (
    DraftDetailDTO,
    DraftGenerateDTO,
    DraftListDTO,
    DraftListItemDTO,
    DraftOutlineDTO,
    DraftResultDTO,
    DraftTemplateDTO,
    DraftVersionDTO,
)
from src.presentation.mappers.query_mapper import to_query_source_response
from src.presentation.schemas.draft import (
    DraftDetailResponse,
    DraftGenerateRequest,
    DraftListItemResponse,
    DraftListResponse,
    DraftOutlineResponse,
    DraftResponse,
    DraftTemplateListResponse,
    DraftTemplateResponse,
    DraftVersionListResponse,
    DraftVersionResponse,
)


def to_draft_generate_dto(body: DraftGenerateRequest, user_id: UUID) -> DraftGenerateDTO:
    tag_names = tuple(tag.strip().lower() for tag in body.tag_names or [] if tag.strip())
    return DraftGenerateDTO(
        user_id=user_id,
        prompt=body.prompt,
        draft_id=body.draft_id,
        template_id=body.template_id,
        scope_type=body.scope_type,
        collection_id=body.collection_id,
        document_ids=tuple(body.document_ids) if body.document_ids else None,
        topic=body.topic,
        knowledge_gap_id=body.knowledge_gap_id,
        outline=tuple(body.outline) if body.outline else None,
        tag_names=tag_names or None,
        document_types=tuple(body.document_types) if body.document_types else None,
        limit=body.limit,
    )


def to_draft_response(dto: DraftResultDTO) -> DraftResponse:
    return DraftResponse(
        draft_id=dto.draft_id,
        version_id=dto.version_id,
        version_number=dto.version_number,
        prompt=dto.prompt,
        template_id=dto.template_id,
        scope_type=dto.scope_type,
        markdown=dto.markdown,
        sources=[to_query_source_response(source, index) for index, source in enumerate(dto.sources, start=1)],
        gaps=dto.gaps,
    )


def to_draft_list_response(dto: DraftListDTO) -> DraftListResponse:
    return DraftListResponse(items=[to_draft_list_item_response(item) for item in dto.items], total=dto.total)


def to_draft_list_item_response(dto: DraftListItemDTO) -> DraftListItemResponse:
    return DraftListItemResponse(
        id=dto.id,
        collection_id=dto.collection_id,
        title=dto.title,
        prompt=dto.prompt,
        template_id=dto.template_id,
        scope_type=dto.scope_type,
        topic=dto.topic,
        knowledge_gap_id=dto.knowledge_gap_id,
        version_number=dto.version_number,
        created_at=dto.created_at.isoformat(),
        updated_at=dto.updated_at.isoformat() if dto.updated_at else None,
    )


def to_draft_detail_response(dto: DraftDetailDTO) -> DraftDetailResponse:
    return DraftDetailResponse(
        id=dto.id,
        collection_id=dto.collection_id,
        current_version_id=dto.current_version_id,
        title=dto.title,
        prompt=dto.prompt,
        template_id=dto.template_id,
        scope_type=dto.scope_type,
        topic=dto.topic,
        knowledge_gap_id=dto.knowledge_gap_id,
        scope_metadata=dto.scope_metadata,
        markdown=dto.markdown,
        sources=[to_query_source_response(source, index) for index, source in enumerate(dto.sources, start=1)],
        gaps=dto.gaps,
        version_number=dto.version_number,
        created_at=dto.created_at.isoformat(),
        updated_at=dto.updated_at.isoformat() if dto.updated_at else None,
    )


def to_draft_version_list_response(items: list[DraftVersionDTO]) -> DraftVersionListResponse:
    return DraftVersionListResponse(items=[to_draft_version_response(item) for item in items])


def to_draft_version_response(dto: DraftVersionDTO) -> DraftVersionResponse:
    return DraftVersionResponse(
        id=dto.id,
        draft_id=dto.draft_id,
        version_number=dto.version_number,
        title=dto.title,
        prompt=dto.prompt,
        template_id=dto.template_id,
        scope_type=dto.scope_type,
        collection_id=dto.collection_id,
        topic=dto.topic,
        knowledge_gap_id=dto.knowledge_gap_id,
        markdown=dto.markdown,
        sources=[to_query_source_response(source, index) for index, source in enumerate(dto.sources, start=1)],
        gaps=dto.gaps,
        created_at=dto.created_at.isoformat(),
    )


def to_draft_template_list_response(items: list[DraftTemplateDTO]) -> DraftTemplateListResponse:
    return DraftTemplateListResponse(items=[to_draft_template_response(item) for item in items])


def to_draft_template_response(dto: DraftTemplateDTO) -> DraftTemplateResponse:
    return DraftTemplateResponse(
        id=dto.id,
        name=dto.name,
        description=dto.description,
        prompt=dto.prompt,
        outline=dto.outline,
    )


def to_draft_outline_response(dto: DraftOutlineDTO) -> DraftOutlineResponse:
    return DraftOutlineResponse(
        prompt=dto.prompt,
        template_id=dto.template_id,
        scope_type=dto.scope_type,
        title=dto.title,
        sections=dto.sections,
    )
