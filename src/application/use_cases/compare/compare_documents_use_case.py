import json
import re
from dataclasses import dataclass
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from src.application.dtos.compare_dtos import (
    CompareDocumentsDTO,
    CompareEvidenceRowDTO,
    CompareListDTO,
    CompareResultDTO,
    DeleteCompareResultDTO,
    GetCompareResultDTO,
    ListCompareResultsDTO,
)
from src.application.dtos.query_dtos import QueryDTO, QuerySourceDTO
from src.application.ports.ai.llm_service import ILLMService
from src.application.ports.persistence.unit_of_work import IUnitOfWork
from src.application.services.document_context_fallback import refrag_context_from_sources, trim_words
from src.application.use_cases.documents.base import ensure_document_owner
from src.application.use_cases.query.query_use_case import QueryUseCase
from src.domain.entities.chunk_entity import ChunkEntity
from src.domain.entities.document_entity import DocumentEntity
from src.domain.exceptions import DocumentNotFoundException, QueryValidationException, ResourceNotFoundException

DEFAULT_COMPARE_DIMENSIONS = ("claims", "assumptions", "architecture", "tradeoffs", "contradictions", "missing_details")
COMPARE_DIMENSION_LABELS = {
    "claims": "Claims",
    "assumptions": "Assumptions",
    "architecture": "Architecture",
    "tradeoffs": "Tradeoffs",
    "contradictions": "Contradictions",
    "missing_details": "Missing details",
}


class CompareDocumentsUseCase:
    def __init__(self, query_use_case: QueryUseCase, uow: IUnitOfWork, llm_service: ILLMService) -> None:
        self._query_use_case = query_use_case
        self._uow = uow
        self._llm_service = llm_service

    async def __call__(self, dto: CompareDocumentsDTO) -> CompareResultDTO:
        if dto.left_document_id == dto.right_document_id:
            raise QueryValidationException("choose two different documents")

        left_document, right_document = await self._load_documents(dto)
        dimensions = normalize_dimensions(dto.dimensions)
        retrieval_query = compare_retrieval_query(left_document, right_document, dto.prompt)
        prompt = compare_prompt(left_document, right_document, dto.prompt, dimensions)
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
        sources = used_sources or result.sources
        if sources:
            return await self._persist_result(
                dto=dto,
                left_document=left_document,
                right_document=right_document,
                markdown=result.answer,
                dimensions=dimensions,
                sources=sources,
            )

        direct_sources = await self._load_direct_sources(
            left_document,
            right_document,
            limit=max(dto.limit, 8),
        )
        answer = await self._llm_service.synthesize_answer(
            query=prompt,
            context=refrag_context_from_sources(prompt, direct_sources),
        )
        return await self._persist_result(
            dto=dto,
            left_document=left_document,
            right_document=right_document,
            markdown=answer,
            dimensions=dimensions,
            sources=direct_sources,
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

    async def _persist_result(
        self,
        *,
        dto: CompareDocumentsDTO,
        left_document: DocumentEntity,
        right_document: DocumentEntity,
        markdown: str,
        dimensions: list[str],
        sources: list[QuerySourceDTO],
    ) -> CompareResultDTO:
        result = CompareResultDTO(
            id=uuid4(),
            user_id=dto.user_id,
            collection_id=shared_collection_id(left_document, right_document),
            left_document_id=left_document.id,
            right_document_id=right_document.id,
            left_title=left_document.title,
            right_title=right_document.title,
            dimensions=dimensions,
            markdown=markdown,
            summary=compare_summary(left_document, right_document, dimensions),
            evidence_rows=await build_evidence_rows(
                llm_service=self._llm_service,
                markdown=markdown,
                dimensions=dimensions,
                left_document_id=left_document.id,
                right_document_id=right_document.id,
                sources=sources,
            ),
            sources=sources,
        )
        async with self._uow:
            created = await self._uow.compare_repo.create(result)
            await self._uow.commit()
        return created


class ListCompareResultsUseCase:
    def __init__(self, uow: IUnitOfWork) -> None:
        self._uow = uow

    async def __call__(self, dto: ListCompareResultsDTO) -> CompareListDTO:
        async with self._uow:
            items = await self._uow.compare_repo.list_by_user_id(
                user_id=dto.user_id,
                collection_id=dto.collection_id,
                limit=dto.limit,
                offset=dto.offset,
            )
            total = await self._uow.compare_repo.count_by_user_id(
                user_id=dto.user_id,
                collection_id=dto.collection_id,
            )
        return CompareListDTO(items=items, total=total)


class GetCompareResultUseCase:
    def __init__(self, uow: IUnitOfWork) -> None:
        self._uow = uow

    async def __call__(self, dto: GetCompareResultDTO) -> CompareResultDTO:
        async with self._uow:
            result = await self._uow.compare_repo.get_by_id(dto.comparison_id)
        if result is None or result.user_id != dto.user_id:
            raise ResourceNotFoundException("comparison not found")
        return result


class DeleteCompareResultUseCase:
    def __init__(self, uow: IUnitOfWork) -> None:
        self._uow = uow

    async def __call__(self, dto: DeleteCompareResultDTO) -> None:
        async with self._uow:
            result = await self._uow.compare_repo.get_by_id(dto.comparison_id)
            if result is None or result.user_id != dto.user_id:
                raise ResourceNotFoundException("comparison not found")
            await self._uow.compare_repo.delete(dto.comparison_id)
            await self._uow.commit()


def compare_prompt(
    left_document: DocumentEntity,
    right_document: DocumentEntity,
    prompt: str | None,
    dimensions: list[str],
) -> str:
    extra_focus = f"\nFocus: {prompt.strip()}" if prompt and prompt.strip() else ""
    dimension_text = ", ".join(COMPARE_DIMENSION_LABELS[dimension] for dimension in dimensions)
    return (
        "Compare these two saved Conserium documents using only retrieved saved context.\n"
        f"Left document: {left_document.title}\n"
        f"Right document: {right_document.title}"
        f"{extra_focus}\n"
        f"Cover these dimensions: {dimension_text}.\n"
        "Return Markdown with these sections: Summary, Evidence by dimension, Decision notes, Source notes. "
        "In Evidence by dimension, include one subsection per requested dimension and cite every row with inline citations like [1], [2]. "
        "If context is insufficient, state the missing context."
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


def normalize_dimensions(dimensions: tuple[str, ...] | None) -> list[str]:
    if not dimensions:
        return list(DEFAULT_COMPARE_DIMENSIONS)
    normalized = []
    for dimension in dimensions:
        key = dimension.strip().lower().replace("-", "_")
        if key not in COMPARE_DIMENSION_LABELS:
            raise QueryValidationException(f"unsupported compare dimension: {dimension}")
        if key not in normalized:
            normalized.append(key)
    return normalized or list(DEFAULT_COMPARE_DIMENSIONS)


def shared_collection_id(left_document: DocumentEntity, right_document: DocumentEntity) -> UUID | None:
    if left_document.collection_id and left_document.collection_id == right_document.collection_id:
        return left_document.collection_id
    return None


def compare_summary(left_document: DocumentEntity, right_document: DocumentEntity, dimensions: list[str]) -> str:
    labels = ", ".join(COMPARE_DIMENSION_LABELS[dimension].lower() for dimension in dimensions[:3])
    suffix = " and more" if len(dimensions) > 3 else ""
    return f"{left_document.title} vs {right_document.title} across {labels}{suffix}."


async def build_evidence_rows(
    *,
    llm_service: ILLMService,
    markdown: str,
    dimensions: list[str],
    left_document_id: UUID,
    right_document_id: UUID,
    sources: list[QuerySourceDTO],
) -> list[CompareEvidenceRowDTO]:
    indexed_sources = [
        IndexedSource(index=index, citation=f"[{index}]", source=source)
        for index, source in enumerate(sources, start=1)
    ]
    structured_rows = await structured_evidence_rows(
        llm_service=llm_service,
        markdown=markdown,
        dimensions=dimensions,
        left_document_id=left_document_id,
        right_document_id=right_document_id,
        sources=indexed_sources,
    )
    if structured_rows:
        return structured_rows
    return [
        evidence_row_for_dimension(
            dimension=dimension,
            markdown=markdown,
            left_document_id=left_document_id,
            right_document_id=right_document_id,
            sources=indexed_sources,
        )
        for dimension in dimensions
    ]


@dataclass(frozen=True, slots=True)
class IndexedSource:
    index: int
    citation: str
    source: QuerySourceDTO


async def structured_evidence_rows(
    *,
    llm_service: ILLMService,
    markdown: str,
    dimensions: list[str],
    left_document_id: UUID,
    right_document_id: UUID,
    sources: list[IndexedSource],
) -> list[CompareEvidenceRowDTO]:
    if not sources:
        return []
    prompt = structured_evidence_prompt(
        markdown=markdown,
        dimensions=dimensions,
        left_document_id=left_document_id,
        right_document_id=right_document_id,
        sources=sources,
    )
    try:
        raw = await llm_service.synthesize_answer(
            query=prompt,
            context=refrag_context_from_sources(prompt, [source.source for source in sources]),
        )
    except Exception:
        return []
    return parse_structured_evidence_rows(
        raw,
        dimensions=dimensions,
        left_document_id=left_document_id,
        right_document_id=right_document_id,
        sources=sources,
    )


def structured_evidence_prompt(
    *,
    markdown: str,
    dimensions: list[str],
    left_document_id: UUID,
    right_document_id: UUID,
    sources: list[IndexedSource],
) -> str:
    source_lines = "\n".join(
        (
            f"{source.citation} source_id={source.source.chunk_id} "
            f"document_id={source.source.document_id} title={source.source.document_title!r}"
        )
        for source in sources
    )
    return (
        "Build a grounded comparison evidence table from the answer and cited sources.\n"
        f"Left document id: {left_document_id}\n"
        f"Right document id: {right_document_id}\n"
        f"Dimensions: {', '.join(dimensions)}\n"
        f"Sources:\n{source_lines}\n\n"
        f"Answer:\n{markdown}\n\n"
        "Return JSON only: an array with one object per dimension. "
        "Each object must include dimension, left_source_id, right_source_id, left_citation, right_citation, "
        "left_evidence, right_evidence, assessment, confidence, and rationale. "
        "Use null when a side has no cited source. Use only the listed source ids and citation numbers."
    )


def parse_structured_evidence_rows(
    raw: str,
    *,
    dimensions: list[str],
    left_document_id: UUID,
    right_document_id: UUID,
    sources: list[IndexedSource],
) -> list[CompareEvidenceRowDTO]:
    payload = _json_payload(raw)
    if not isinstance(payload, list):
        return []
    by_dimension = dict.fromkeys(dimensions)
    source_by_id = {source.source.chunk_id: source for source in sources}
    for item in payload:
        if not isinstance(item, dict):
            continue
        dimension = str(item.get("dimension") or "").strip().lower().replace("-", "_").replace(" ", "_")
        if dimension not in by_dimension:
            continue
        left_source = _source_from_structured_item(item.get("left_source_id"), source_by_id, left_document_id)
        right_source = _source_from_structured_item(item.get("right_source_id"), source_by_id, right_document_id)
        by_dimension[dimension] = CompareEvidenceRowDTO(
            dimension=dimension,
            left_evidence=_string_or_none(item.get("left_evidence")) or evidence_text(left_source),
            right_evidence=_string_or_none(item.get("right_evidence")) or evidence_text(right_source),
            assessment=_string_or_none(item.get("assessment")) or evidence_assessment(dimension, left_source, right_source),
            left_source_id=left_source.source.chunk_id if left_source is not None else None,
            right_source_id=right_source.source.chunk_id if right_source is not None else None,
            left_citation=left_source.citation if left_source is not None else None,
            right_citation=right_source.citation if right_source is not None else None,
            confidence=_confidence_or_none(item.get("confidence")),
            rationale=_string_or_none(item.get("rationale")),
        )
    rows = [row for row in by_dimension.values() if row is not None]
    return rows if len(rows) == len(dimensions) else []


def evidence_row_for_dimension(
    *,
    dimension: str,
    markdown: str,
    left_document_id: UUID,
    right_document_id: UUID,
    sources: list[IndexedSource],
) -> CompareEvidenceRowDTO:
    cited = cited_sources_for_dimension(markdown, dimension, sources)
    left = best_cited_evidence(cited, document_id=left_document_id)
    right = best_cited_evidence(cited, document_id=right_document_id)
    assessment = evidence_assessment(dimension, left, right)
    return CompareEvidenceRowDTO(
        dimension=dimension,
        left_evidence=evidence_text(left),
        right_evidence=evidence_text(right),
        assessment=assessment,
        left_source_id=left.source.chunk_id if left is not None else None,
        right_source_id=right.source.chunk_id if right is not None else None,
        left_citation=left.citation if left is not None else None,
        right_citation=right.citation if right is not None else None,
        confidence=0.35 if left is not None or right is not None else 0.0,
        rationale=f"Heuristic fallback from cited answer text. {assessment}",
    )


def cited_sources_for_dimension(markdown: str, dimension: str, sources: list[IndexedSource]) -> list[IndexedSource]:
    window = dimension_window(markdown, dimension)
    if not window:
        return []
    cited_indexes = {int(match) for match in re.findall(r"\[(\d+)\]", window)}
    return [source for source in sources if source.index in cited_indexes]


def dimension_window(markdown: str, dimension: str) -> str:
    label = COMPARE_DIMENSION_LABELS[dimension].lower()
    lines = markdown.splitlines()
    for index, line in enumerate(lines):
        normalized = line.strip("#*:- ").lower()
        if label in normalized or dimension.replace("_", " ") in normalized:
            return "\n".join(lines[index : index + 6])
    return markdown


def best_cited_evidence(sources: list[IndexedSource], *, document_id: UUID) -> IndexedSource | None:
    sources = [source for source in sources if source.source.document_id == document_id]
    if not sources:
        return None
    ranked = sorted(
        sources,
        key=lambda source: source.source.score or 0,
        reverse=True,
    )
    return ranked[0]


def evidence_text(source: IndexedSource | None) -> str | None:
    if source is None:
        return None
    return f"{source.citation} {trim_words(source.source.content, 45)}"


def evidence_assessment(dimension: str, left_source: IndexedSource | None, right_source: IndexedSource | None) -> str:
    label = COMPARE_DIMENSION_LABELS[dimension]
    if left_source and right_source:
        return f"{label} comparison is grounded in {left_source.citation} and {right_source.citation}."
    if left_source:
        return f"{label} has evidence from the left document only: {left_source.citation}."
    if right_source:
        return f"{label} has evidence from the right document only: {right_source.citation}."
    return f"{label} has no direct supporting source."


def _json_payload(raw: str) -> object:
    text = raw.strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL | re.IGNORECASE)
    if fenced:
        text = fenced.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def _source_from_structured_item(
    value: object,
    source_by_id: dict[UUID, IndexedSource],
    expected_document_id: UUID,
) -> IndexedSource | None:
    if value is None:
        return None
    try:
        source_id = UUID(str(value))
    except ValueError:
        return None
    source = source_by_id.get(source_id)
    if source is None or source.source.document_id != expected_document_id:
        return None
    return source


def _string_or_none(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _confidence_or_none(value: object) -> float | None:
    if value is None:
        return None
    if not isinstance(value, int | float | str):
        return None
    try:
        confidence = float(value)
    except (TypeError, ValueError):
        return None
    return max(0.0, min(1.0, confidence))
