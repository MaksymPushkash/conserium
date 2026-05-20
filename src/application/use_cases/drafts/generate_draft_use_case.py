from uuid import NAMESPACE_URL, uuid5

from src.application.dtos.draft_dtos import DraftGenerateDTO, DraftResultDTO
from src.application.dtos.query_dtos import QueryDTO, QuerySourceDTO
from src.application.ports.ai.llm_service import ILLMService
from src.application.ports.persistence.unit_of_work import IUnitOfWork
from src.application.services.document_context_fallback import refrag_context_from_sources, trim_words
from src.application.use_cases.query.query_use_case import QueryUseCase
from src.domain.exceptions import QueryValidationException
from src.domain.value_objects.document_status import DocumentStatus


class GenerateDraftUseCase:
    def __init__(self, query_use_case: QueryUseCase, uow: IUnitOfWork, llm_service: ILLMService) -> None:
        self._query_use_case = query_use_case
        self._uow = uow
        self._llm_service = llm_service

    async def __call__(self, dto: DraftGenerateDTO) -> DraftResultDTO:
        prompt = dto.prompt.strip()
        if not prompt:
            raise QueryValidationException("draft prompt cannot be empty")

        result = await self._query_use_case(draft_query_dto(dto, prompt, relevance_query=prompt, limit=max(dto.limit, 12)))
        gaps = draft_gaps(result.answer)
        if gaps:
            fallback_sources = await self._fallback_sources(dto)
            if fallback_sources:
                fallback_context = refrag_context_from_sources(draft_query(prompt), fallback_sources)
                answer = await self._llm_service.synthesize_answer(query=draft_query(prompt), context=fallback_context)
                return DraftResultDTO(
                    prompt=prompt,
                    markdown=answer,
                    sources=fallback_sources,
                    gaps=draft_gaps(answer),
                )
        return DraftResultDTO(
            prompt=prompt,
            markdown=result.answer,
            sources=[source for source in result.sources if source.used_in_answer],
            gaps=gaps,
        )

    async def _fallback_sources(self, dto: DraftGenerateDTO) -> list[QuerySourceDTO]:
        async with self._uow:
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


def draft_query_dto(dto: DraftGenerateDTO, prompt: str, *, relevance_query: str, limit: int) -> QueryDTO:
    return QueryDTO(
        user_id=dto.user_id,
        query=draft_query(prompt),
        retrieval_query=prompt,
        relevance_query=relevance_query,
        collection_id=dto.collection_id,
        tag_names=dto.tag_names,
        document_types=dto.document_types,
        limit=limit,
        retrieval_depth="deep",
    )


def draft_query(prompt: str) -> str:
    return (
        "Write a Markdown draft using only my saved Cortex materials.\n"
        f"Draft request: {prompt}\n"
        "Requirements:\n"
        "- Use only retrieved saved context.\n"
        "- Include inline citations like [1], [2] for factual claims.\n"
        "- If the saved context is insufficient, say what is missing instead of inventing.\n"
        "- Return only the draft body."
    )


def draft_gaps(markdown: str) -> list[str]:
    normalized = markdown.casefold()
    if "does not contain enough relevant information" in normalized or "could not find relevant saved context" in normalized:
        return ["Saved context is insufficient for this draft."]
    return []

