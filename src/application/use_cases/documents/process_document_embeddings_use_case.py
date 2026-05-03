from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any
from uuid import UUID

from src.domain.entities.chunk_entity import ChunkEntity

if TYPE_CHECKING:
    from src.application.ports.ai.embedding_provider import IEmbeddingProvider
    from src.application.ports.cache.document_status_cache import IDocumentStatusCache
    from src.application.ports.persistence.unit_of_work import IUnitOfWork
    from src.domain.entities.document_entity import DocumentEntity


@dataclass(frozen=True, slots=True)
class ProcessDocumentEmbeddingsResult:
    document_id: str
    status: str


class ProcessDocumentEmbeddingsUseCase:
    def __init__(
        self,
        uow: IUnitOfWork,
        status_cache: IDocumentStatusCache,
        embedding_provider: IEmbeddingProvider,
    ) -> None:
        self._uow = uow
        self._status_cache = status_cache
        self._embedding_provider = embedding_provider

    async def __call__(
        self,
        *,
        document_id: str,
        raw_text: str,
        chunks_data: list[dict[str, Any]],
        expected_content_hash: str | None = None,
    ) -> ProcessDocumentEmbeddingsResult:
        document = await self._load_document(document_id)
        if document is None:
            return ProcessDocumentEmbeddingsResult(document_id=document_id, status="NOT_FOUND")
        if _is_stale_text_job(document, expected_content_hash):
            return ProcessDocumentEmbeddingsResult(document_id=document_id, status="STALE")

        await self._status_cache.set_status(
            document.id,
            status="PROCESSING",
            progress=70,
            message="Generating embeddings...",
        )
        document.mark_processing()

        embeddings = await self._embedding_provider.embed_texts(
            [str(chunk["content"]) for chunk in chunks_data]
        )

        await self._status_cache.set_status(
            document.id,
            status="PROCESSING",
            progress=90,
            message="Saving to database...",
        )

        chunk_entities = _build_chunk_entities(document.id, chunks_data, embeddings)
        document.update_content(
            raw_content=document.raw_content or raw_text,
            word_count=len(raw_text.split()),
            language=document.language,
        )
        document.mark_ready()

        async with self._uow:
            await self._uow.chunk_repo.delete_by_document_id(document.id)
            await self._uow.chunk_repo.create_batch(chunk_entities)
            await self._uow.document_repo.update(document)
            await self._uow.commit()

        await self._status_cache.set_status(
            document.id,
            status="READY",
            progress=100,
            message="Processing complete.",
        )
        return ProcessDocumentEmbeddingsResult(document_id=document_id, status="READY")

    async def _load_document(self, document_id: str) -> DocumentEntity | None:
        async with self._uow:
            return await self._uow.document_repo.get_by_id(UUID(document_id))


def _build_chunk_entities(
    document_id: UUID,
    chunks_data: list[dict[str, Any]],
    embeddings: list[list[float]],
) -> list[ChunkEntity]:
    return [
        ChunkEntity.create(
            id=uuid.uuid4(),
            document_id=document_id,
            content=str(chunk["content"]),
            embedding=embedding,
            chunk_index=int(chunk["chunk_index"]),
            start_char=_optional_int(chunk.get("start_char")),
            end_char=_optional_int(chunk.get("end_char")),
            page_number=_optional_int(chunk.get("page_number")),
            token_count=_optional_int(chunk.get("token_count")),
        )
        for chunk, embedding in zip(chunks_data, embeddings, strict=True)
    ]


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    return int(value)


def _is_stale_text_job(document: DocumentEntity, expected_content_hash: str | None) -> bool:
    if expected_content_hash is None:
        return False
    current_content = document.raw_content
    if current_content is None:
        return False
    return _content_hash(current_content) != expected_content_hash


def _content_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
