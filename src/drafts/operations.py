from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import NAMESPACE_URL, uuid4, uuid5

from src.documents.services.context_fallback import refrag_context_from_sources, trim_words
from src.documents.status import DocumentStatus
from src.drafts.helpers import (
    TEMPLATES,
    draft_detail,
    draft_list_item,
    draft_query,
    draft_query_input,
    draft_template,
    draft_title,
    draft_version,
    normalize_outline,
    normalize_scope,
    scope_metadata,
)
from src.drafts.helpers import (
    has_sufficient_draft_context as has_sufficient_draft_context,
)
from src.drafts.repository import DraftRecord, DraftVersionRecord
from src.drafts.schemas import (
    DraftDetail,
    DraftGenerationInput,
    DraftListResult,
    DraftOutline,
    DraftResult,
    DraftTemplate,
    DraftVersion,
)
from src.kit.exceptions import DocumentNotFoundException, QueryValidationException, ResourceNotFoundException
from src.query.schemas import QuerySource

if TYPE_CHECKING:
    from uuid import UUID

    from src.documents.document_repository import DocumentRepository
    from src.drafts.repository import DraftRepository
    from src.kit.ai.llm_service import LLMService
    from src.postgres import AsyncSession
    from src.query.service import QueryExecutor


class DraftGenerator:
    def __init__(
        self,
        query_executor: QueryExecutor,
        session: AsyncSession,
        draft_repo: DraftRepository,
        document_repo: DocumentRepository,
        llm_service: LLMService,
    ) -> None:
        self._query_executor = query_executor
        self._session = session
        self._draft_repo = draft_repo
        self._document_repo = document_repo
        self._llm_service = llm_service

    async def __call__(self, dto: DraftGenerationInput) -> DraftResult:
        prompt = dto.prompt.strip()
        if not prompt:
            raise QueryValidationException("draft prompt cannot be empty")
        scope = normalize_scope(dto)
        template = draft_template(dto.template_id)
        outline = normalize_outline(dto.outline) or template.outline

        result = await self._query_executor(
            draft_query_input(
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
        scope: DraftGenerationInput,
        prompt: str,
        template: DraftTemplate,
        markdown: str,
        sources: list[QuerySource],
        gaps: list[str],
    ) -> DraftResult:
        existing = None
        if scope.draft_id is not None:
            existing = await self._draft_repo.get_by_id(scope.draft_id)
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
            await self._draft_repo.append_version(draft_id=draft_id, version=version)
            if existing
            else await self._draft_repo.create_with_version(draft=record, version=version)
        )
        await self._session.flush()
        return DraftResult(
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

    async def _fallback_sources(self, dto: DraftGenerationInput) -> list[QuerySource]:
        if dto.document_ids:
            documents = []
            for document_id in dto.document_ids:
                document = await self._document_repo.get_by_id(document_id)
                if document is None or document.user_id != dto.user_id:
                    raise DocumentNotFoundException("document not found")
                if document.status == DocumentStatus.READY:
                    documents.append(document)
        else:
            documents = []
            document_types = dto.document_types or (None,)
            for document_type in document_types:
                documents.extend(
                    await self._document_repo.get_by_user_id(
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
        sources: list[QuerySource] = []
        seen_documents = set()
        for document in documents:
            if document.id in seen_documents:
                continue
            seen_documents.add(document.id)
            content = document.summary or document.raw_content
            if not content:
                continue
            sources.append(
                QuerySource(
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


def list_draft_templates() -> list[DraftTemplate]:
    return list(TEMPLATES.values())


def generate_draft_outline(dto: DraftGenerationInput) -> DraftOutline:
    prompt = dto.prompt.strip()
    if not prompt:
        raise QueryValidationException("draft prompt cannot be empty")
    scope = normalize_scope(dto)
    template = draft_template(dto.template_id)
    return DraftOutline(
        prompt=prompt,
        template_id=template.id,
        scope_type=scope.scope_type,
        title=draft_title(prompt, template),
        sections=normalize_outline(dto.outline) or template.outline,
    )


async def list_drafts(
    draft_repo: DraftRepository,
    *,
    user_id: UUID,
    collection_id: UUID | None = None,
    limit: int = 20,
    offset: int = 0,
) -> DraftListResult:
    records = await draft_repo.list_by_user_id(
        user_id=user_id,
        collection_id=collection_id,
        limit=limit,
        offset=offset,
    )
    return DraftListResult(items=[draft_list_item(record) for record in records], total=len(records))


async def get_draft(draft_repo: DraftRepository, *, user_id: UUID, draft_id: UUID) -> DraftDetail:
    record = await draft_repo.get_by_id(draft_id)
    if record is None or record.user_id != user_id:
        raise ResourceNotFoundException("draft not found")
    return draft_detail(record)


async def list_draft_versions(
    draft_repo: DraftRepository,
    *,
    user_id: UUID,
    draft_id: UUID,
) -> list[DraftVersion]:
    draft = await draft_repo.get_by_id(draft_id)
    if draft is None or draft.user_id != user_id:
        raise ResourceNotFoundException("draft not found")
    versions = await draft_repo.list_versions(draft_id=draft_id, user_id=user_id)
    return [draft_version(version) for version in versions]


async def restore_draft_version(
    session: AsyncSession,
    draft_repo: DraftRepository,
    *,
    user_id: UUID,
    draft_id: UUID,
    version_id: UUID,
) -> DraftDetail:
    version = await draft_repo.get_version(draft_id=draft_id, version_id=version_id, user_id=user_id)
    if version is None:
        raise ResourceNotFoundException("draft version not found")
    restored = await draft_repo.restore_version(version=version)
    await session.flush()
    return draft_detail(restored)


async def delete_draft(
    session: AsyncSession,
    draft_repo: DraftRepository,
    *,
    user_id: UUID,
    draft_id: UUID,
) -> None:
    draft = await draft_repo.get_by_id(draft_id)
    if draft is None or draft.user_id != user_id:
        raise ResourceNotFoundException("draft not found")
    await draft_repo.delete(draft_id)
    await session.flush()
