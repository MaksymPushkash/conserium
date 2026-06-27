from __future__ import annotations

from typing import TYPE_CHECKING

from src.documents.results import document_result
from src.documents.schemas import DocumentSearchResult, DocumentSearchResults

if TYPE_CHECKING:
    from collections.abc import Sequence
    from uuid import UUID

    from src.documents.chunk_repository import ChunkRepository
    from src.documents.document_repository import DocumentRepository
    from src.documents.repository import ChunkSearchResult
    from src.documents.status import DocumentStatus
    from src.documents.types import DocumentType
    from src.kit.ai.embedding_provider import EmbeddingProvider


class DocumentSearchService:
    def __init__(
        self,
        document_repo: DocumentRepository,
        chunk_repo: ChunkRepository,
        embedding_provider: EmbeddingProvider,
    ) -> None:
        self._document_repo = document_repo
        self._chunk_repo = chunk_repo
        self._embedding_provider = embedding_provider

    async def search(
        self,
        *,
        user_id: UUID,
        query: str,
        limit: int = 20,
        collection_id: UUID | None = None,
        status: DocumentStatus | None = None,
        document_type: DocumentType | None = None,
        tag_name: str | None = None,
    ) -> DocumentSearchResults:
        query = query.strip()
        if not query:
            return DocumentSearchResults(items=[], query=query, total=0, limit=limit)
        normalized_tag = tag_name.strip().lower() if tag_name else None

        embedding = await self._embedding_provider.embed_text(query)
        chunk_results = await self._chunk_repo.hybrid_search(
            query=query,
            embedding=embedding,
            user_id=user_id,
            limit=max(limit * 4, limit),
            collection_id=collection_id,
            tag_names=(normalized_tag,) if normalized_tag else None,
            document_types=(document_type,) if document_type else None,
        )
        results = await self._document_results(chunk_results, user_id=user_id, status=status)

        return DocumentSearchResults(items=[*results[:limit]], query=query, total=len(results), limit=limit)

    async def _document_results(
        self,
        chunk_results: Sequence[ChunkSearchResult],
        *,
        user_id: UUID,
        status: DocumentStatus | None,
    ) -> Sequence[DocumentSearchResult]:
        best_chunks = _best_chunk_by_document(chunk_results)
        results = []
        for document_id, chunk_result in best_chunks.items():
            document = await self._document_repo.get_by_id(document_id)
            if document is None or document.user_id != user_id:
                continue
            if status is not None and document.status != status:
                continue
            results.append(
                DocumentSearchResult(
                    document=document_result(document),
                    snippet=chunk_result.chunk.content,
                    score=chunk_result.score,
                    chunk_id=chunk_result.chunk.id,
                    page_number=chunk_result.chunk.page_number,
                )
            )
        return results


def _best_chunk_by_document(chunk_results: Sequence[ChunkSearchResult]) -> dict[UUID, ChunkSearchResult]:
    best_chunks: dict[UUID, ChunkSearchResult] = {}
    for result in chunk_results:
        document_id = result.chunk.document_id
        if document_id not in best_chunks:
            best_chunks[document_id] = result
    return best_chunks


__all__ = ["DocumentSearchService"]
