from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID  # noqa: TC003

from fastapi import Depends

from src.documents.document_repository import DocumentRepository
from src.drafts.operations import (
    DraftGenerator,
    delete_draft,
    generate_draft_outline,
    get_draft,
    list_draft_templates,
    list_draft_versions,
    list_drafts,
    restore_draft_version,
)
from src.drafts.repository import DraftRepository
from src.drafts.schemas import (
    DraftDetailResponse,
    DraftGenerateDTO,
    DraftGenerateRequest,
    DraftListItemResponse,
    DraftListResponse,
    DraftOutlineResponse,
    DraftResponse,
    DraftTemplateListResponse,
    DraftTemplateResponse,
    DraftVersionListResponse,
    DraftVersionResponse,
    QuerySourceResponse,
)
from src.postgres import AsyncSession, get_db_session
from src.query.service import get_llm_service, get_query_executor

if TYPE_CHECKING:
    from src.drafts.schemas import (
        DraftDetailDTO,
        DraftListDTO,
        DraftListItemDTO,
        DraftOutlineDTO,
        DraftResultDTO,
        DraftTemplateDTO,
        DraftVersionDTO,
    )
    from src.kit.ports.ai.llm_service import ILLMService
    from src.query.schemas import QuerySourceDTO
    from src.query.service import QueryExecutor


class DraftService:
    def __init__(
        self,
        session: AsyncSession,
        draft_repo: DraftRepository,
        document_repo: DocumentRepository,
        query_executor: QueryExecutor,
        llm_service: ILLMService,
    ) -> None:
        self._session = session
        self._draft_repo = draft_repo
        self._document_repo = document_repo
        self._query_executor = query_executor
        self._llm_service = llm_service

    async def list(
        self,
        *,
        user_id: UUID,
        collection_id: UUID | None,
        limit: int,
        offset: int,
    ) -> DraftListResponse:
        result = await list_drafts(
            self._draft_repo,
            user_id=user_id,
            collection_id=collection_id,
            limit=limit,
            offset=offset,
        )
        return to_draft_list_response(result)

    async def list_templates(self) -> DraftTemplateListResponse:
        result = list_draft_templates()
        return to_draft_template_list_response(result)

    async def generate_outline(self, *, user_id: UUID, body: DraftGenerateRequest) -> DraftOutlineResponse:
        result = generate_draft_outline(to_draft_generate_dto(body, user_id))
        return to_draft_outline_response(result)

    async def generate(self, *, user_id: UUID, body: DraftGenerateRequest) -> DraftResponse:
        result = await DraftGenerator(
            self._query_executor,
            self._session,
            self._draft_repo,
            self._document_repo,
            self._llm_service,
        )(to_draft_generate_dto(body, user_id))
        return to_draft_response(result)

    async def get(self, *, user_id: UUID, draft_id: UUID) -> DraftDetailResponse:
        result = await get_draft(self._draft_repo, user_id=user_id, draft_id=draft_id)
        return to_draft_detail_response(result)

    async def list_versions(self, *, user_id: UUID, draft_id: UUID) -> DraftVersionListResponse:
        result = await list_draft_versions(self._draft_repo, user_id=user_id, draft_id=draft_id)
        return to_draft_version_list_response(result)

    async def restore_version(self, *, user_id: UUID, draft_id: UUID, version_id: UUID) -> DraftDetailResponse:
        result = await restore_draft_version(
            self._session,
            self._draft_repo,
            user_id=user_id,
            draft_id=draft_id,
            version_id=version_id,
        )
        return to_draft_detail_response(result)

    async def delete(self, *, user_id: UUID, draft_id: UUID) -> None:
        await delete_draft(self._session, self._draft_repo, user_id=user_id, draft_id=draft_id)


def get_query_executor_for_drafts(query_executor: QueryExecutor = Depends(get_query_executor)) -> QueryExecutor:
    return query_executor


def get_llm_service_for_drafts(llm_service: ILLMService = Depends(get_llm_service)) -> ILLMService:
    return llm_service


def get_draft_service(
    session: AsyncSession = Depends(get_db_session),
    query_executor: QueryExecutor = Depends(get_query_executor_for_drafts),
    llm_service: ILLMService = Depends(get_llm_service_for_drafts),
) -> DraftService:
    return DraftService(
        session,
        DraftRepository(session),
        DocumentRepository.from_session(session),
        query_executor,
        llm_service,
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
        sources=[to_draft_query_source_response(source, index) for index, source in enumerate(dto.sources, start=1)],
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
        sources=[to_draft_query_source_response(source, index) for index, source in enumerate(dto.sources, start=1)],
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
        sources=[to_draft_query_source_response(source, index) for index, source in enumerate(dto.sources, start=1)],
        gaps=dto.gaps,
        created_at=dto.created_at.isoformat(),
    )


def to_draft_template_list_response(items: list[DraftTemplateDTO]) -> DraftTemplateListResponse:
    return DraftTemplateListResponse(items=[to_draft_template_response(item) for item in items])


def to_draft_query_source_response(dto: QuerySourceDTO, index: int) -> QuerySourceResponse:
    return QuerySourceResponse(
        chunk_id=dto.chunk_id,
        document_id=dto.document_id,
        document_title=dto.document_title,
        content=dto.content,
        page_number=dto.page_number,
        chunk_index=dto.chunk_index,
        score=dto.score,
        citation=f"[{index}]",
        used_in_answer=dto.used_in_answer,
    )


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


__all__ = [
    "DraftService",
    "get_draft_service",
    "to_draft_detail_response",
    "to_draft_generate_dto",
    "to_draft_list_response",
    "to_draft_outline_response",
    "to_draft_response",
    "to_draft_template_list_response",
    "to_draft_version_list_response",
]
