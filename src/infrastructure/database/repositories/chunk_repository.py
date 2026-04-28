from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.application.interfaces.chunk_repository import IChunkRepository
from src.domain.entities.chunk_entity import ChunkEntity
from src.infrastructure.database.models.chunk import ChunkModel
from src.infrastructure.database.models.document import DocumentModel


class SQLAlchemyChunkRepository(IChunkRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, chunk_id: UUID) -> ChunkEntity | None:
        result = await self._session.execute(select(ChunkModel).where(ChunkModel.id == chunk_id))
        model = result.scalar_one_or_none()
        return self._to_entity(model) if model else None

    async def get_by_document_id(self, document_id: UUID) -> list[ChunkEntity]:
        result = await self._session.execute(
            select(ChunkModel).where(ChunkModel.document_id == document_id).order_by(ChunkModel.chunk_index.asc())
        )
        return [self._to_entity(model) for model in result.scalars().all()]

    async def create_batch(self, chunks: list[ChunkEntity]) -> None:
        self._session.add_all([self._to_model(chunk) for chunk in chunks])

    async def delete_by_document_id(self, document_id: UUID) -> None:
        await self._session.execute(delete(ChunkModel).where(ChunkModel.document_id == document_id))

    async def semantic_search(
        self,
        embedding: list[float],
        user_id: UUID,
        *,
        limit: int = 10,
        collection_id: UUID | None = None,
    ) -> list[ChunkEntity]:
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
        return [self._to_entity(model) for model in result.scalars().all()]

    def _to_entity(self, model: ChunkModel) -> ChunkEntity:
        return ChunkEntity(
            id=model.id,
            document_id=model.document_id,
            content=model.content,
            embedding=list(model.embedding),
            chunk_index=model.chunk_index,
            start_char=model.start_char,
            end_char=model.end_char,
            page_number=model.page_number,
            token_count=model.token_count,
            created_at=model.created_at,
        )

    def _to_model(self, entity: ChunkEntity) -> ChunkModel:
        return ChunkModel(
            id=entity.id,
            document_id=entity.document_id,
            content=entity.content,
            embedding=entity.embedding,
            chunk_index=entity.chunk_index,
            start_char=entity.start_char,
            end_char=entity.end_char,
            page_number=entity.page_number,
            token_count=entity.token_count,
            created_at=entity.created_at,
        )

    @staticmethod
    def _validate_search_embedding(embedding: list[float]) -> None:
        if len(embedding) != ChunkEntity.EMBEDDING_DIMENSIONS:
            raise ValueError(f"embedding must have {ChunkEntity.EMBEDDING_DIMENSIONS} dimensions")
