from uuid import UUID

from src.application.dtos.draft_dtos import DraftGenerateDTO, DraftResultDTO
from src.presentation.mappers.query_mapper import to_query_source_response
from src.presentation.schemas.draft import DraftGenerateRequest, DraftResponse


def to_draft_generate_dto(body: DraftGenerateRequest, user_id: UUID) -> DraftGenerateDTO:
    tag_names = tuple(tag.strip().lower() for tag in body.tag_names or [] if tag.strip())
    return DraftGenerateDTO(
        user_id=user_id,
        prompt=body.prompt,
        collection_id=body.collection_id,
        tag_names=tag_names or None,
        document_types=tuple(body.document_types) if body.document_types else None,
        limit=body.limit,
    )


def to_draft_response(dto: DraftResultDTO) -> DraftResponse:
    return DraftResponse(
        prompt=dto.prompt,
        markdown=dto.markdown,
        sources=[to_query_source_response(source, index) for index, source in enumerate(dto.sources, start=1)],
        gaps=dto.gaps,
    )
