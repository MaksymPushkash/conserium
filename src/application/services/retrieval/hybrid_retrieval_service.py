from uuid import UUID

from src.application.dtos.query_dtos import QuerySourceDTO
from src.application.ports.ai.embedding_provider import IEmbeddingProvider
from src.application.ports.persistence.unit_of_work import IUnitOfWork
from src.domain.value_objects.document_type import DocumentType


class HybridRetrievalService:
    def __init__(
        self,
        uow: IUnitOfWork,
        embedding_provider: IEmbeddingProvider,
    ) -> None:
        self._uow = uow
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
    ) -> list[QuerySourceDTO]:
        embedding = await self._embedding_provider.embed_text(query)
        async with self._uow:
            results = await self._uow.chunk_repo.hybrid_search(
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
            QuerySourceDTO(
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
