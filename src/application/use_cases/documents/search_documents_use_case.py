from uuid import UUID

from src.application.dtos.document_dtos import DocumentSearchDTO, DocumentSearchResultDTO, SearchDocumentsDTO
from src.application.ports.ai.embedding_provider import IEmbeddingProvider
from src.application.ports.persistence.chunk_repository import ChunkSearchResult
from src.application.ports.persistence.unit_of_work import IUnitOfWork
from src.application.use_cases.documents.base import document_to_dto


class SearchDocumentsUseCase:
    def __init__(self, uow: IUnitOfWork, embedding_provider: IEmbeddingProvider) -> None:
        self._uow = uow
        self._embedding_provider = embedding_provider

    async def __call__(self, dto: SearchDocumentsDTO) -> DocumentSearchDTO:
        query = dto.query.strip()
        if not query:
            return DocumentSearchDTO(items=[], query=query, total=0, limit=dto.limit)

        embedding = await self._embedding_provider.embed_text(query)
        async with self._uow:
            chunk_results = await self._uow.chunk_repo.hybrid_search(
                query=query,
                embedding=embedding,
                user_id=dto.user_id,
                limit=max(dto.limit * 4, dto.limit),
                collection_id=dto.collection_id,
                tag_names=(dto.tag_name,) if dto.tag_name else None,
                document_types=(dto.document_type,) if dto.document_type else None,
            )
            results = await self._document_results(chunk_results, dto)

        return DocumentSearchDTO(items=results[: dto.limit], query=query, total=len(results), limit=dto.limit)

    async def _document_results(
        self,
        chunk_results: list[ChunkSearchResult],
        dto: SearchDocumentsDTO,
    ) -> list[DocumentSearchResultDTO]:
        best_chunks = self._best_chunk_by_document(chunk_results)
        results: list[DocumentSearchResultDTO] = []
        for document_id, chunk_result in best_chunks.items():
            document = await self._uow.document_repo.get_by_id(document_id)
            if document is None or document.user_id != dto.user_id:
                continue
            if dto.status is not None and document.status != dto.status:
                continue
            results.append(
                DocumentSearchResultDTO(
                    document=document_to_dto(document),
                    snippet=chunk_result.chunk.content,
                    score=chunk_result.score,
                    chunk_id=chunk_result.chunk.id,
                    page_number=chunk_result.chunk.page_number,
                )
            )
        return results

    @staticmethod
    def _best_chunk_by_document(chunk_results: list[ChunkSearchResult]) -> dict[UUID, ChunkSearchResult]:
        best_chunks: dict[UUID, ChunkSearchResult] = {}
        for result in chunk_results:
            document_id = result.chunk.document_id
            if document_id not in best_chunks:
                best_chunks[document_id] = result
        return best_chunks
