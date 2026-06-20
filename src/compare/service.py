from uuid import UUID, uuid4

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.compare.helpers import (
    build_evidence_rows,
    compare_prompt,
    compare_retrieval_query,
    compare_summary,
    normalize_dimensions,
    shared_collection_id,
    source_from_document,
    sources_from_chunks,
)
from src.compare.repository import CompareRepository
from src.compare.schemas import (
    CompareDocumentsDTO,
    CompareDocumentsRequest,
    CompareDocumentsResponse,
    CompareEvidenceRowResponse,
    CompareListDTO,
    CompareListResponse,
    CompareResultDTO,
)
from src.documents.chunk_repository import ChunkRepository
from src.documents.document_repository import DocumentRepository
from src.documents.services.context_fallback import refrag_context_from_sources
from src.kit.exceptions import (
    DocumentAccessDeniedException,
    DocumentNotFoundException,
    QueryValidationException,
    ResourceNotFoundException,
)
from src.kit.ports.ai.llm_service import ILLMService
from src.models.document import DocumentModel
from src.query.schemas import QueryDTO, QuerySourceDTO, QuerySourceResponse
from src.query.service import QueryExecutor, get_llm_service, get_query_executor


class CompareService:
    async def compare_documents(
        self,
        session: AsyncSession,
        *,
        query_executor: QueryExecutor,
        llm_service: ILLMService,
        dto: CompareDocumentsDTO,
    ) -> CompareDocumentsResponse:
        if dto.left_document_id == dto.right_document_id:
            raise QueryValidationException("choose two different documents")

        left_document, right_document = await self._load_documents(session, dto)
        dimensions = normalize_dimensions(dto.dimensions)
        retrieval_query = compare_retrieval_query(left_document, right_document, dto.prompt)
        prompt = compare_prompt(left_document, right_document, dto.prompt, dimensions)
        await session.flush()

        result = await query_executor(
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
        if not sources:
            sources = await self._load_direct_sources(
                session,
                left_document,
                right_document,
                limit=max(dto.limit, 8),
            )
            markdown = await llm_service.synthesize_answer(
                query=prompt,
                context=refrag_context_from_sources(prompt, sources),
            )
        else:
            markdown = result.answer

        persisted = await self._persist_result(
            session,
            llm_service=llm_service,
            dto=dto,
            left_document=left_document,
            right_document=right_document,
            markdown=markdown,
            dimensions=dimensions,
            sources=sources,
        )
        return to_compare_documents_response(persisted)

    async def list_results(
        self,
        session: AsyncSession,
        *,
        user_id: UUID,
        collection_id: UUID | None,
        limit: int,
        offset: int,
    ) -> CompareListResponse:
        repository = CompareRepository(session)
        result = CompareListDTO(
            items=await repository.list_by_user_id(
                user_id=user_id,
                collection_id=collection_id,
                limit=limit,
                offset=offset,
            ),
            total=await repository.count_by_user_id(user_id=user_id, collection_id=collection_id),
        )
        return to_compare_list_response(result)

    async def get_result(self, session: AsyncSession, *, user_id: UUID, comparison_id: UUID) -> CompareDocumentsResponse:
        repository = CompareRepository(session)
        result = await repository.get_by_id(comparison_id)
        if result is None or result.user_id != user_id:
            raise ResourceNotFoundException("comparison not found")
        return to_compare_documents_response(result)

    async def delete_result(self, session: AsyncSession, *, user_id: UUID, comparison_id: UUID) -> None:
        repository = CompareRepository(session)
        result = await repository.get_by_id(comparison_id)
        if result is None or result.user_id != user_id:
            raise ResourceNotFoundException("comparison not found")
        await repository.delete(comparison_id)
        await session.flush()

    async def _load_documents(
        self,
        session: AsyncSession,
        dto: CompareDocumentsDTO,
    ) -> tuple[DocumentModel, DocumentModel]:
        repository = DocumentRepository.from_session(session)
        left_document = await repository.get_by_id(dto.left_document_id)
        right_document = await repository.get_by_id(dto.right_document_id)
        if left_document is None or right_document is None:
            raise DocumentNotFoundException("document not found")
        _ensure_document_owner(left_document, dto.user_id)
        _ensure_document_owner(right_document, dto.user_id)
        return left_document, right_document

    async def _load_direct_sources(
        self,
        session: AsyncSession,
        left_document: DocumentModel,
        right_document: DocumentModel,
        *,
        limit: int,
    ) -> list[QuerySourceDTO]:
        repository = ChunkRepository.from_session(session)
        left_chunks = await repository.get_by_document_id(left_document.id)
        right_chunks = await repository.get_by_document_id(right_document.id)
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
        session: AsyncSession,
        *,
        llm_service: ILLMService,
        dto: CompareDocumentsDTO,
        left_document: DocumentModel,
        right_document: DocumentModel,
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
                llm_service=llm_service,
                markdown=markdown,
                dimensions=dimensions,
                left_document_id=left_document.id,
                right_document_id=right_document.id,
                sources=sources,
            ),
            sources=sources,
        )
        repository = CompareRepository(session)
        created = await repository.create(result)
        await session.flush()
        return created


def get_compare_query_executor(query_executor: QueryExecutor = Depends(get_query_executor)) -> QueryExecutor:
    return query_executor


def get_compare_llm_service(llm_service: ILLMService = Depends(get_llm_service)) -> ILLMService:
    return llm_service


def get_compare_service() -> CompareService:
    return compare


def to_compare_documents_dto(body: CompareDocumentsRequest, user_id: UUID) -> CompareDocumentsDTO:
    return CompareDocumentsDTO(
        user_id=user_id,
        left_document_id=body.left_document_id,
        right_document_id=body.right_document_id,
        prompt=body.prompt,
        dimensions=tuple(body.dimensions) if body.dimensions else None,
        limit=body.limit,
    )


def to_compare_documents_response(dto: CompareResultDTO) -> CompareDocumentsResponse:
    return CompareDocumentsResponse(
        id=dto.id,
        collection_id=dto.collection_id,
        left_document_id=dto.left_document_id,
        right_document_id=dto.right_document_id,
        left_title=dto.left_title,
        right_title=dto.right_title,
        dimensions=dto.dimensions,
        markdown=dto.markdown,
        summary=dto.summary,
        evidence_rows=[
            CompareEvidenceRowResponse(
                dimension=row.dimension,
                left_evidence=row.left_evidence,
                right_evidence=row.right_evidence,
                assessment=row.assessment,
                left_source_id=row.left_source_id,
                right_source_id=row.right_source_id,
                left_citation=row.left_citation,
                right_citation=row.right_citation,
                confidence=row.confidence,
                rationale=row.rationale,
                grounding_type=row.grounding_type,
            )
            for row in dto.evidence_rows
        ],
        sources=[to_query_source_response(source, index) for index, source in enumerate(dto.sources, start=1)],
        created_at=dto.created_at,
    )


def to_compare_list_response(dto: CompareListDTO) -> CompareListResponse:
    return CompareListResponse(
        items=[to_compare_documents_response(item) for item in dto.items],
        total=dto.total,
    )


def to_query_source_response(dto: QuerySourceDTO, index: int) -> QuerySourceResponse:
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


def _ensure_document_owner(document: DocumentModel, user_id: UUID) -> None:
    if document.user_id != user_id:
        raise DocumentAccessDeniedException("document access denied")


compare = CompareService()

__all__ = [
    "CompareService",
    "compare",
    "get_compare_llm_service",
    "get_compare_query_executor",
    "get_compare_service",
    "to_compare_documents_dto",
    "to_compare_documents_response",
    "to_compare_list_response",
]
