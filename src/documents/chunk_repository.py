from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import delete, func, literal, select

from src.documents.repository import ChunkSearchResult
from src.models.chunk import ChunkModel
from src.models.document import DocumentModel
from src.models.tag import TagModel

if TYPE_CHECKING:
    from uuid import UUID

    from sqlalchemy.ext.asyncio import AsyncSession

    from src.documents.types import DocumentType


class ChunkRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @classmethod
    def from_session(cls, session: AsyncSession) -> ChunkRepository:
        return cls(session)

    async def get_by_id(self, chunk_id: UUID) -> ChunkModel | None:
        result = await self._session.execute(select(ChunkModel).where(ChunkModel.id == chunk_id))
        return result.scalar_one_or_none()

    async def get_by_document_id(self, document_id: UUID) -> list[ChunkModel]:
        result = await self._session.execute(
            select(ChunkModel).where(ChunkModel.document_id == document_id).order_by(ChunkModel.chunk_index.asc())
        )
        return list(result.scalars().all())

    async def create_batch(self, chunks: list[ChunkModel]) -> None:
        self._session.add_all(chunks)

    async def delete_by_document_id(self, document_id: UUID) -> None:
        await self._session.execute(delete(ChunkModel).where(ChunkModel.document_id == document_id))

    async def semantic_search(
        self,
        embedding: list[float],
        user_id: UUID,
        *,
        limit: int = 10,
        collection_id: UUID | None = None,
    ) -> list[ChunkModel]:
        self._validate_search_embedding(embedding)
        distance = ChunkModel.embedding.cosine_distance(embedding)
        statement = (
            select(ChunkModel)
            .join(DocumentModel, ChunkModel.document_id == DocumentModel.id)
            .where(DocumentModel.user_id == user_id)
            .order_by(distance)
            .limit(limit)
        )
        if collection_id is not None:
            statement = statement.where(DocumentModel.collection_id == collection_id)

        result = await self._session.execute(statement)
        return list(result.scalars().all())

    async def hybrid_search(
        self,
        *,
        query: str,
        embedding: list[float],
        user_id: UUID,
        limit: int = 10,
        collection_id: UUID | None = None,
        tag_names: tuple[str, ...] | None = None,
        document_types: tuple[DocumentType, ...] | None = None,
        document_ids: tuple[UUID, ...] | None = None,
    ) -> list[ChunkSearchResult]:
        self._validate_search_embedding(embedding)
        vector_limit = max(limit * 4, limit)
        distance = ChunkModel.embedding.cosine_distance(embedding)
        vector_statement = (
            select(
                ChunkModel,
                DocumentModel.title,
                (literal(1.0) - distance).label("score"),
            )
            .join(DocumentModel, ChunkModel.document_id == DocumentModel.id)
            .where(DocumentModel.user_id == user_id)
            .order_by(distance)
            .limit(vector_limit)
        )
        keyword_statement = self._keyword_statement(
            query,
            user_id,
            limit=vector_limit,
            collection_id=collection_id,
            tag_names=tag_names,
            document_types=document_types,
            document_ids=document_ids,
        )
        if collection_id is not None:
            vector_statement = vector_statement.where(DocumentModel.collection_id == collection_id)
        if tag_names is not None:
            vector_statement = vector_statement.join(DocumentModel.tag_models).where(TagModel.name.in_(tag_names))
        if document_types is not None:
            vector_statement = vector_statement.where(DocumentModel.type.in_([document_type.value for document_type in document_types]))
        if document_ids is not None:
            vector_statement = vector_statement.where(DocumentModel.id.in_(document_ids))

        vector_rows = (await self._session.execute(vector_statement)).all()
        keyword_rows = (await self._session.execute(keyword_statement)).all()

        fused: dict[UUID, tuple[ChunkModel, str | None, float]] = {}
        self._add_rrf_rows(fused, list(vector_rows), weight=1.0)
        self._add_rrf_rows(fused, list(keyword_rows), weight=1.2)

        ranked = sorted(fused.values(), key=lambda item: item[2], reverse=True)[:limit]
        return [
            ChunkSearchResult(
                chunk=chunk_model,
                document_title=document_title,
                score=score,
            )
            for chunk_model, document_title, score in ranked
        ]

    @staticmethod
    def _validate_search_embedding(embedding: list[float]) -> None:
        if len(embedding) != ChunkModel.EMBEDDING_DIMENSIONS:
            raise ValueError(f"embedding must have {ChunkModel.EMBEDDING_DIMENSIONS} dimensions")

    @staticmethod
    def _add_rrf_rows(
        fused: dict[UUID, tuple[ChunkModel, str | None, float]],
        rows: list[Any],
        *,
        weight: float,
    ) -> None:
        for rank, row in enumerate(rows, start=1):
            chunk_model = row[0]
            document_title = row[1]
            row_score = float(row[2] or 0.0)
            rrf_score = weight * (1.0 / (60 + rank)) + row_score * 0.001
            existing = fused.get(chunk_model.id)
            if existing is None:
                fused[chunk_model.id] = (chunk_model, document_title, rrf_score)
                continue
            fused[chunk_model.id] = (existing[0], existing[1], existing[2] + rrf_score)

    @staticmethod
    def _keyword_statement(
        query: str,
        user_id: UUID,
        *,
        limit: int,
        collection_id: UUID | None,
        tag_names: tuple[str, ...] | None,
        document_types: tuple[DocumentType, ...] | None,
        document_ids: tuple[UUID, ...] | None,
    ) -> Any:
        ts_query = func.plainto_tsquery("simple", query)
        search_vector = func.to_tsvector("simple", ChunkModel.content)
        statement = (
            select(
                ChunkModel,
                DocumentModel.title,
                func.ts_rank_cd(search_vector, ts_query).label("score"),
            )
            .join(DocumentModel, ChunkModel.document_id == DocumentModel.id)
            .where(DocumentModel.user_id == user_id)
            .where(search_vector.op("@@")(ts_query))
            .order_by(func.ts_rank_cd(search_vector, ts_query).desc())
            .limit(limit)
        )
        if collection_id is not None:
            statement = statement.where(DocumentModel.collection_id == collection_id)
        if tag_names is not None:
            statement = statement.join(DocumentModel.tag_models).where(TagModel.name.in_(tag_names))
        if document_types is not None:
            statement = statement.where(DocumentModel.type.in_([document_type.value for document_type in document_types]))
        if document_ids is not None:
            statement = statement.where(DocumentModel.id.in_(document_ids))
        return statement
