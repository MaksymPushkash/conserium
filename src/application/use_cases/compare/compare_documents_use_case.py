from uuid import NAMESPACE_URL, UUID, uuid5

from src.application.dtos.compare_dtos import CompareDocumentsDTO, CompareResultDTO
from src.application.dtos.query_dtos import QueryDTO, QuerySourceDTO
from src.application.ports.ai.llm_service import ILLMService
from src.application.ports.persistence.unit_of_work import IUnitOfWork
from src.application.services.document_context_fallback import refrag_context_from_sources, trim_words
from src.application.use_cases.documents.base import ensure_document_owner
from src.application.use_cases.query.query_use_case import QueryUseCase
from src.domain.entities.chunk_entity import ChunkEntity
from src.domain.entities.document_entity import DocumentEntity
from src.domain.exceptions import DocumentNotFoundException, QueryValidationException


class CompareDocumentsUseCase:
    def __init__(self, query_use_case: QueryUseCase, uow: IUnitOfWork, llm_service: ILLMService) -> None:
        self._query_use_case = query_use_case
        self._uow = uow
        self._llm_service = llm_service

    async def __call__(self, dto: CompareDocumentsDTO) -> CompareResultDTO:
        if dto.left_document_id == dto.right_document_id:
            raise QueryValidationException("choose two different documents")

        left_document, right_document = await self._load_documents(dto)
        prompt = compare_prompt(left_document, right_document, dto.prompt)
        direct_sources = await self._load_direct_sources(
            left_document,
            right_document,
            limit=max(dto.limit, 8),
        )
        retrieval_query = compare_retrieval_query(left_document, right_document, dto.prompt)
        try:
            result = await self._query_use_case(
                QueryDTO(
                    user_id=dto.user_id,
                    query=prompt,
                    retrieval_query=retrieval_query,
                    relevance_query="",
                    document_ids=(dto.left_document_id, dto.right_document_id),
                    limit=dto.limit,
                )
            )
            used_sources = [source for source in result.sources if source.used_in_answer]
            sources = used_sources or result.sources or direct_sources
            fallback_answer = result.answer
        except Exception:
            if not direct_sources:
                raise
            sources = direct_sources
            fallback_answer = ""
        if direct_sources:
            context_sources = _rank_direct_sources(direct_sources, sources)
            answer = await self._llm_service.synthesize_answer(
                query=prompt,
                context=refrag_context_from_sources(prompt, context_sources),
            )
            return CompareResultDTO(
                left_document_id=dto.left_document_id,
                right_document_id=dto.right_document_id,
                left_title=left_document.title,
                right_title=right_document.title,
                markdown=answer,
                sources=context_sources,
            )
        return CompareResultDTO(
            left_document_id=dto.left_document_id,
            right_document_id=dto.right_document_id,
            left_title=left_document.title,
            right_title=right_document.title,
            markdown=fallback_answer,
            sources=sources,
        )

    async def _load_documents(self, dto: CompareDocumentsDTO) -> tuple[DocumentEntity, DocumentEntity]:
        async with self._uow:
            left_document = await self._uow.document_repo.get_by_id(dto.left_document_id)
            right_document = await self._uow.document_repo.get_by_id(dto.right_document_id)
        if left_document is None or right_document is None:
            raise DocumentNotFoundException("document not found")
        ensure_document_owner(left_document, dto.user_id)
        ensure_document_owner(right_document, dto.user_id)
        return left_document, right_document

    async def _load_direct_sources(
        self,
        left_document: DocumentEntity,
        right_document: DocumentEntity,
        *,
        limit: int,
    ) -> list[QuerySourceDTO]:
        async with self._uow:
            left_chunks = await self._uow.chunk_repo.get_by_document_id(left_document.id)
            right_chunks = await self._uow.chunk_repo.get_by_document_id(right_document.id)
        sources = [
            *sources_from_chunks(left_document, left_chunks, limit=max(2, limit // 2)),
            *sources_from_chunks(right_document, right_chunks, limit=max(2, limit // 2)),
        ]
        if sources:
            return sources
        return [
            source
            for source in (
                source_from_document(left_document),
                source_from_document(right_document),
            )
            if source is not None
        ]


def compare_prompt(left_document: DocumentEntity, right_document: DocumentEntity, prompt: str | None) -> str:
    extra_focus = f"\nFocus: {prompt.strip()}" if prompt and prompt.strip() else ""
    return (
        "Compare these two saved Cortex documents using only retrieved saved context.\n"
        f"Left document: {left_document.title}\n"
        f"Right document: {right_document.title}"
        f"{extra_focus}\n"
        "Return Markdown with these sections: Shared ideas, Key differences, Possible contradictions, Source notes. "
        "Use inline citations like [1], [2]. If context is insufficient, state the missing context."
    )


def compare_retrieval_query(left_document: DocumentEntity, right_document: DocumentEntity, prompt: str | None) -> str:
    parts = [
        left_document.title,
        right_document.title,
        left_document.summary or "",
        right_document.summary or "",
        prompt or "",
    ]
    return " ".join(part for part in parts if part.strip())


def _rank_direct_sources(direct_sources: list[QuerySourceDTO], ranked_sources: list[QuerySourceDTO]) -> list[QuerySourceDTO]:
    direct_by_id = {source.chunk_id: source for source in direct_sources}
    ordered = [direct_by_id[source.chunk_id] for source in ranked_sources if source.chunk_id in direct_by_id]
    seen = {source.chunk_id for source in ordered}
    ordered.extend(source for source in direct_sources if source.chunk_id not in seen)
    return ordered


def sources_from_chunks(document: DocumentEntity, chunks: list[ChunkEntity], *, limit: int) -> list[QuerySourceDTO]:
    return [
        QuerySourceDTO(
            chunk_id=chunk.id,
            document_id=document.id,
            document_title=document.title,
            content=chunk.content,
            page_number=chunk.page_number,
            chunk_index=chunk.chunk_index,
            score=1.0,
            used_in_answer=True,
        )
        for chunk in chunks[:limit]
        if chunk.content.strip()
    ]


def source_from_document(document: DocumentEntity) -> QuerySourceDTO | None:
    content = document.summary or document.raw_content
    if not content:
        return None
    return QuerySourceDTO(
        chunk_id=stable_document_source_id(document.id),
        document_id=document.id,
        document_title=document.title,
        content=trim_words(content, 900),
        page_number=None,
        chunk_index=0,
        score=1.0,
        used_in_answer=True,
    )


def stable_document_source_id(document_id: UUID) -> UUID:
    return uuid5(NAMESPACE_URL, f"compare-fallback:{document_id}")
