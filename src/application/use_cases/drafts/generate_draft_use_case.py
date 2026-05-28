from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

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
from src.application.dtos.query_dtos import QueryDTO, QuerySourceDTO
from src.application.ports.ai.llm_service import ILLMService
from src.application.ports.persistence.draft_repository import DraftRecord, DraftVersionRecord
from src.application.ports.persistence.unit_of_work import IUnitOfWork
from src.application.services.document_context_fallback import refrag_context_from_sources, trim_words
from src.application.use_cases.query.query_use_case import QueryUseCase
from src.domain.exceptions import DocumentNotFoundException, QueryValidationException, ResourceNotFoundException
from src.domain.value_objects.document_status import DocumentStatus

_TEMPLATES = {
    "brief": DraftTemplateDTO(
        id="brief",
        name="Brief",
        description="Concise cited summary for quick decision-making.",
        prompt="Write a concise brief with context, key points, risks, and next actions.",
        outline=["Context", "Key points", "Risks", "Next actions"],
    ),
    "prd": DraftTemplateDTO(
        id="prd",
        name="PRD",
        description="Product requirements with problem, goals, scope, and acceptance criteria.",
        prompt="Write a PRD with problem, goals, users, requirements, non-goals, and acceptance criteria.",
        outline=["Problem", "Goals", "Users", "Requirements", "Non-goals", "Acceptance criteria"],
    ),
    "study_guide": DraftTemplateDTO(
        id="study_guide",
        name="Study guide",
        description="Structured learning material with concepts, examples, and checks.",
        prompt="Write a study guide with concepts, explanations, examples, and review questions.",
        outline=["Learning goals", "Core concepts", "Examples", "Common mistakes", "Review questions"],
    ),
    "comparison_memo": DraftTemplateDTO(
        id="comparison_memo",
        name="Comparison memo",
        description="Side-by-side memo focused on tradeoffs and recommendation.",
        prompt="Write a comparison memo covering options, evidence, tradeoffs, risks, and recommendation.",
        outline=["Options", "Evidence", "Tradeoffs", "Risks", "Recommendation"],
    ),
    "implementation_plan": DraftTemplateDTO(
        id="implementation_plan",
        name="Implementation plan",
        description="Ordered engineering plan with phases, risks, and validation.",
        prompt="Write an implementation plan with phases, concrete tasks, risks, and validation.",
        outline=["Objective", "Phases", "Tasks", "Risks", "Validation"],
    ),
}

_SCOPE_TYPES = {"all", "documents", "collection", "topic", "knowledge_gap"}


class GenerateDraftUseCase:
    def __init__(self, query_use_case: QueryUseCase, uow: IUnitOfWork, llm_service: ILLMService) -> None:
        self._query_use_case = query_use_case
        self._uow = uow
        self._llm_service = llm_service

    async def __call__(self, dto: DraftGenerateDTO) -> DraftResultDTO:
        prompt = dto.prompt.strip()
        if not prompt:
            raise QueryValidationException("draft prompt cannot be empty")
        scope = normalize_scope(dto)
        template = draft_template(dto.template_id)
        outline = normalize_outline(dto.outline) or template.outline

        result = await self._query_use_case(
            draft_query_dto(
                scope,
                prompt,
                template=template,
                outline=outline,
                relevance_query=prompt,
                limit=max(dto.limit, 12),
            )
        )
        if not has_sufficient_draft_context(result.sources):
            fallback_sources = await self._fallback_sources(scope)
            if fallback_sources:
                query = draft_query(prompt, template=template, outline=outline, scope=scope)
                fallback_context = refrag_context_from_sources(query, fallback_sources)
                answer = await self._llm_service.synthesize_answer(query=query, context=fallback_context)
                return await self._persist_result(
                    scope=scope,
                    prompt=prompt,
                    template=template,
                    markdown=answer,
                    sources=fallback_sources,
                    gaps=[],
                )
            gaps = ["Saved context is insufficient for this draft."]
        else:
            gaps = []
        return await self._persist_result(
            scope=scope,
            prompt=prompt,
            template=template,
            markdown=result.answer,
            sources=[source for source in result.sources if source.used_in_answer],
            gaps=gaps,
        )

    async def _persist_result(
        self,
        *,
        scope: DraftGenerateDTO,
        prompt: str,
        template: DraftTemplateDTO,
        markdown: str,
        sources: list[QuerySourceDTO],
        gaps: list[str],
    ) -> DraftResultDTO:
        async with self._uow:
            existing = None
            if scope.draft_id is not None:
                existing = await self._uow.draft_repo.get_by_id(scope.draft_id)
                if existing is None or existing.user_id != scope.user_id:
                    raise ResourceNotFoundException("draft not found")
            draft_id = existing.id if existing else uuid4()
            version_number = (existing.version_number + 1) if existing else 1
            version_id = uuid4()
            title = draft_title(prompt, template)
            record = DraftRecord(
                id=draft_id,
                user_id=scope.user_id,
                collection_id=scope.collection_id,
                title=title,
                prompt=prompt,
                template_id=template.id,
                scope_type=scope.scope_type,
                topic=scope.topic,
                knowledge_gap_id=scope.knowledge_gap_id,
                scope_metadata=scope_metadata(scope),
                markdown=markdown,
                sources=sources,
                gaps=gaps,
                current_version_id=version_id,
                version_number=version_number,
                created_at=existing.created_at if existing else None,
                updated_at=None,
            )
            version = DraftVersionRecord(
                id=version_id,
                draft_id=draft_id,
                user_id=scope.user_id,
                version_number=version_number,
                title=title,
                prompt=prompt,
                template_id=template.id,
                scope_type=scope.scope_type,
                collection_id=scope.collection_id,
                topic=scope.topic,
                knowledge_gap_id=scope.knowledge_gap_id,
                scope_metadata=scope_metadata(scope),
                markdown=markdown,
                sources=sources,
                gaps=gaps,
                created_at=None,
            )
            saved = (
                await self._uow.draft_repo.append_version(draft_id=draft_id, version=version)
                if existing
                else await self._uow.draft_repo.create_with_version(draft=record, version=version)
            )
            await self._uow.commit()
        return DraftResultDTO(
            draft_id=saved.id,
            version_id=saved.current_version_id,
            version_number=saved.version_number,
            prompt=saved.prompt,
            template_id=template.id,
            scope_type=saved.scope_type,
            markdown=saved.markdown,
            sources=saved.sources,
            gaps=gaps,
        )

    async def _fallback_sources(self, dto: DraftGenerateDTO) -> list[QuerySourceDTO]:
        async with self._uow:
            if dto.document_ids:
                documents = []
                for document_id in dto.document_ids:
                    document = await self._uow.document_repo.get_by_id(document_id)
                    if document is None or document.user_id != dto.user_id:
                        raise DocumentNotFoundException("document not found")
                    if document.status == DocumentStatus.READY:
                        documents.append(document)
            else:
                documents = []
                document_types = dto.document_types or (None,)
                for document_type in document_types:
                    documents.extend(
                        await self._uow.document_repo.get_by_user_id(
                            dto.user_id,
                            limit=max(dto.limit, 8),
                            document_type=document_type,
                            collection_id=dto.collection_id,
                            status=DocumentStatus.READY,
                        )
                    )
            if dto.tag_names:
                tags = {tag.casefold() for tag in dto.tag_names}
                documents = [
                    document
                    for document in documents
                    if tags.intersection({tag.casefold() for tag in document.tags})
                ]
        sources: list[QuerySourceDTO] = []
        seen_documents = set()
        for document in documents:
            if document.id in seen_documents:
                continue
            seen_documents.add(document.id)
            content = document.summary or document.raw_content
            if not content:
                continue
            sources.append(
                QuerySourceDTO(
                    chunk_id=uuid5(NAMESPACE_URL, f"draft-fallback:{document.id}"),
                    document_id=document.id,
                    document_title=document.title,
                    content=trim_words(content, 900),
                    page_number=None,
                    chunk_index=0,
                    score=1.0,
                    used_in_answer=True,
                )
            )
            if len(sources) >= max(dto.limit, 8):
                break
        return sources


class ListDraftTemplatesUseCase:
    async def __call__(self) -> list[DraftTemplateDTO]:
        return list(_TEMPLATES.values())


class GenerateDraftOutlineUseCase:
    async def __call__(self, dto: DraftGenerateDTO) -> DraftOutlineDTO:
        prompt = dto.prompt.strip()
        if not prompt:
            raise QueryValidationException("draft prompt cannot be empty")
        scope = normalize_scope(dto)
        template = draft_template(dto.template_id)
        return DraftOutlineDTO(
            prompt=prompt,
            template_id=template.id,
            scope_type=scope.scope_type,
            title=draft_title(prompt, template),
            sections=normalize_outline(dto.outline) or template.outline,
        )


class ListDraftsUseCase:
    def __init__(self, uow: IUnitOfWork) -> None:
        self._uow = uow

    async def __call__(
        self,
        *,
        user_id: UUID,
        collection_id: UUID | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> DraftListDTO:
        async with self._uow:
            records = await self._uow.draft_repo.list_by_user_id(
                user_id=user_id,
                collection_id=collection_id,
                limit=limit,
                offset=offset,
            )
        return DraftListDTO(items=[draft_list_item(record) for record in records], total=len(records))


class GetDraftUseCase:
    def __init__(self, uow: IUnitOfWork) -> None:
        self._uow = uow

    async def __call__(self, *, user_id: UUID, draft_id: UUID) -> DraftDetailDTO:
        async with self._uow:
            record = await self._uow.draft_repo.get_by_id(draft_id)
        if record is None or record.user_id != user_id:
            raise ResourceNotFoundException("draft not found")
        return draft_detail(record)


class ListDraftVersionsUseCase:
    def __init__(self, uow: IUnitOfWork) -> None:
        self._uow = uow

    async def __call__(self, *, user_id: UUID, draft_id: UUID) -> list[DraftVersionDTO]:
        async with self._uow:
            draft = await self._uow.draft_repo.get_by_id(draft_id)
            if draft is None or draft.user_id != user_id:
                raise ResourceNotFoundException("draft not found")
            versions = await self._uow.draft_repo.list_versions(draft_id=draft_id, user_id=user_id)
        return [draft_version(version) for version in versions]


class RestoreDraftVersionUseCase:
    def __init__(self, uow: IUnitOfWork) -> None:
        self._uow = uow

    async def __call__(self, *, user_id: UUID, draft_id: UUID, version_id: UUID) -> DraftDetailDTO:
        async with self._uow:
            version = await self._uow.draft_repo.get_version(draft_id=draft_id, version_id=version_id, user_id=user_id)
            if version is None:
                raise ResourceNotFoundException("draft version not found")
            restored = await self._uow.draft_repo.restore_version(version=version)
            await self._uow.commit()
        return draft_detail(restored)


class DeleteDraftUseCase:
    def __init__(self, uow: IUnitOfWork) -> None:
        self._uow = uow

    async def __call__(self, *, user_id: UUID, draft_id: UUID) -> None:
        async with self._uow:
            draft = await self._uow.draft_repo.get_by_id(draft_id)
            if draft is None or draft.user_id != user_id:
                raise ResourceNotFoundException("draft not found")
            await self._uow.draft_repo.delete(draft_id)
            await self._uow.commit()


def draft_query_dto(
    dto: DraftGenerateDTO,
    prompt: str,
    *,
    template: DraftTemplateDTO,
    outline: list[str],
    relevance_query: str,
    limit: int,
) -> QueryDTO:
    return QueryDTO(
        user_id=dto.user_id,
        query=draft_query(prompt, template=template, outline=outline, scope=dto),
        retrieval_query=prompt,
        relevance_query=relevance_query,
        collection_id=dto.collection_id,
        tag_names=dto.tag_names,
        document_types=dto.document_types,
        document_ids=dto.document_ids,
        limit=limit,
        retrieval_depth="deep",
    )


def draft_list_item(record: DraftRecord) -> DraftListItemDTO:
    if record.created_at is None:
        raise ValueError("draft created_at is required")
    return DraftListItemDTO(
        id=record.id,
        collection_id=record.collection_id,
        title=record.title,
        prompt=record.prompt,
        template_id=record.template_id,
        scope_type=record.scope_type,
        topic=record.topic,
        knowledge_gap_id=record.knowledge_gap_id,
        version_number=record.version_number,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def draft_detail(record: DraftRecord) -> DraftDetailDTO:
    if record.created_at is None:
        raise ValueError("draft created_at is required")
    return DraftDetailDTO(
        id=record.id,
        collection_id=record.collection_id,
        current_version_id=record.current_version_id,
        title=record.title,
        prompt=record.prompt,
        template_id=record.template_id,
        scope_type=record.scope_type,
        topic=record.topic,
        knowledge_gap_id=record.knowledge_gap_id,
        scope_metadata=record.scope_metadata,
        markdown=record.markdown,
        sources=record.sources,
        gaps=record.gaps,
        version_number=record.version_number,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def draft_version(record: DraftVersionRecord) -> DraftVersionDTO:
    if record.created_at is None:
        raise ValueError("draft version created_at is required")
    return DraftVersionDTO(
        id=record.id,
        draft_id=record.draft_id,
        version_number=record.version_number,
        title=record.title,
        prompt=record.prompt,
        template_id=record.template_id,
        scope_type=record.scope_type,
        collection_id=record.collection_id,
        topic=record.topic,
        knowledge_gap_id=record.knowledge_gap_id,
        markdown=record.markdown,
        sources=record.sources,
        gaps=record.gaps,
        created_at=record.created_at,
    )


def draft_query(prompt: str, *, template: DraftTemplateDTO, outline: list[str], scope: DraftGenerateDTO) -> str:
    outline_text = "\n".join(f"- {section}" for section in outline)
    return (
        "Write a Markdown draft using only my saved Conserium materials.\n"
        f"Template: {template.name}\n"
        f"Template instructions: {template.prompt}\n"
        f"Scope: {scope_description(scope)}\n"
        f"Draft request: {prompt}\n"
        "Outline:\n"
        f"{outline_text}\n"
        "Requirements:\n"
        "- Use only retrieved saved context.\n"
        "- Include inline citations like [1], [2] for factual claims.\n"
        "- If the saved context is insufficient, say what is missing instead of inventing.\n"
        "- Return only the draft body."
    )


def has_sufficient_draft_context(sources: list[QuerySourceDTO]) -> bool:
    return any(source.used_in_answer for source in sources)


def normalize_scope(dto: DraftGenerateDTO) -> DraftGenerateDTO:
    scope_type = dto.scope_type.strip().lower() if dto.scope_type else "all"
    if scope_type not in _SCOPE_TYPES:
        raise QueryValidationException("unsupported draft scope")
    if dto.document_ids:
        scope_type = "documents"
    elif dto.collection_id is not None and scope_type == "all":
        scope_type = "collection"
    elif dto.topic and scope_type == "all":
        scope_type = "topic"
    elif dto.knowledge_gap_id and scope_type == "all":
        scope_type = "knowledge_gap"

    topic = dto.topic.strip().lower() if dto.topic else None
    tag_names = tuple(tag.strip().lower() for tag in dto.tag_names or () if tag.strip())
    if topic and topic not in tag_names:
        tag_names = (*tag_names, topic)

    if scope_type == "documents" and not dto.document_ids:
        raise QueryValidationException("document scope requires document_ids")
    if scope_type == "collection" and dto.collection_id is None:
        raise QueryValidationException("collection scope requires collection_id")
    if scope_type == "topic" and not topic:
        raise QueryValidationException("topic scope requires topic")
    if scope_type == "knowledge_gap":
        if not dto.knowledge_gap_id:
            raise QueryValidationException("knowledge gap scope requires knowledge_gap_id")
        if not topic:
            raise QueryValidationException("knowledge gap scope requires topic")

    return DraftGenerateDTO(
        user_id=dto.user_id,
        prompt=dto.prompt,
        draft_id=dto.draft_id,
        template_id=dto.template_id,
        scope_type=scope_type,
        collection_id=dto.collection_id,
        document_ids=dto.document_ids,
        topic=topic,
        knowledge_gap_id=dto.knowledge_gap_id,
        outline=dto.outline,
        tag_names=tag_names or None,
        document_types=dto.document_types,
        limit=dto.limit,
    )


def draft_template(template_id: str) -> DraftTemplateDTO:
    template = _TEMPLATES.get(template_id.strip().lower())
    if template is None:
        raise QueryValidationException("unsupported draft template")
    return template


def normalize_outline(outline: tuple[str, ...] | None) -> list[str]:
    return [section.strip()[:120] for section in outline or () if section.strip()]


def draft_title(prompt: str, template: DraftTemplateDTO) -> str:
    normalized = " ".join(prompt.split())
    return f"{template.name}: {normalized[:80]}"


def scope_description(dto: DraftGenerateDTO) -> str:
    if dto.scope_type == "documents":
        return f"selected documents only ({len(dto.document_ids or ())} document(s))"
    if dto.scope_type == "collection":
        return f"collection {dto.collection_id}"
    if dto.scope_type == "topic":
        return f"topic {dto.topic}"
    if dto.scope_type == "knowledge_gap":
        return f"knowledge gap {dto.knowledge_gap_id} for topic {dto.topic}"
    return "all saved workspace sources"


def scope_metadata(dto: DraftGenerateDTO) -> dict[str, object]:
    return {
        "scope_type": dto.scope_type,
        "collection_id": str(dto.collection_id) if dto.collection_id else None,
        "document_ids": [str(document_id) for document_id in dto.document_ids or ()],
        "topic": dto.topic,
        "knowledge_gap_id": dto.knowledge_gap_id,
        "tag_names": list(dto.tag_names or ()),
        "document_types": [document_type.value for document_type in dto.document_types or ()],
        "limit": dto.limit,
    }
