from uuid import UUID

from src.documents.chunk_repository import ChunkRepository
from src.documents.types import DocumentType
from src.kit.ai.embedding_provider import EmbeddingProvider
from src.query.schemas import QuerySource


class HybridRetrievalService:
    def __init__(
        self,
        chunk_repo: ChunkRepository,
        embedding_provider: EmbeddingProvider,
    ) -> None:
        self._chunk_repo = chunk_repo
        self._embedding_provider = embedding_provider

    async def retrieve(
        self,
        *,
        query: str,
        user_id: UUID,
        limit: int,
        collection_id: UUID | None,
        tag_names: tuple[str, ...] | None = None,
        document_types: tuple[DocumentType, ...] | None = None,
        document_ids: tuple[UUID, ...] | None = None,
    ) -> list[QuerySource]:
        embedding = await self._embedding_provider.embed_text(query)
        results = await self._chunk_repo.hybrid_search(
            query=query,
            embedding=embedding,
            user_id=user_id,
            limit=limit,
            collection_id=collection_id,
            tag_names=tag_names,
            document_types=document_types,
            document_ids=document_ids,
        )

        return [
            QuerySource(
                chunk_id=result.chunk.id,
                document_id=result.chunk.document_id,
                document_title=result.document_title,
                content=result.chunk.content,
                page_number=result.chunk.page_number,
                chunk_index=result.chunk.chunk_index,
                score=result.score,
            )
            for result in results
        ]
