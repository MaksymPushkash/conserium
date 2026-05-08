from __future__ import annotations

from typing import TYPE_CHECKING

from src.core.config import settings

if TYPE_CHECKING:
    from uuid import UUID

    from src.application.ports.ai.embedding_provider import IEmbeddingProvider
    from src.application.ports.persistence.unit_of_work import IUnitOfWork
    from src.domain.entities.chunk_entity import ChunkEntity
    from src.domain.entities.document_entity import DocumentEntity


class DocumentEmbeddingService:
    def __init__(
        self,
        uow: IUnitOfWork,
        embedding_provider: IEmbeddingProvider,
        *,
        full_text_max_chars: int | None = None,
    ) -> None:
        self._uow = uow
        self._embedding_provider = embedding_provider
        self._full_text_max_chars = (
            settings.ENRICHMENT_FULL_TEXT_EMBEDDING_MAX_CHARS
            if full_text_max_chars is None
            else full_text_max_chars
        )

    async def ensure_embedding(self, document: DocumentEntity) -> None:
        if document.doc_embedding is not None:
            return

        text = document.raw_content or ""
        if not text:
            return

        chunk_embeddings = [
            chunk.embedding
            for chunk in await self._get_document_chunks(document.id)
            if chunk.embedding
        ]
        if chunk_embeddings:
            document.update_embedding(_mean_embedding(chunk_embeddings))
            return

        if len(text) <= self._full_text_max_chars:
            document.update_embedding(await self._embedding_provider.embed_text(text))

    async def _get_document_chunks(self, document_id: UUID) -> list[ChunkEntity]:
        async with self._uow:
            return await self._uow.chunk_repo.get_by_document_id(document_id)


def _mean_embedding(embeddings: list[list[float]]) -> list[float]:
    if not embeddings:
        return []
    dimension = len(embeddings[0])
    return [
        sum(embedding[index] for embedding in embeddings) / len(embeddings)
        for index in range(dimension)
    ]
