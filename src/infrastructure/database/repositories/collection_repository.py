from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.application.ports.persistence.collection_repository import ICollectionRepository
from src.domain.entities.collection_entity import CollectionEntity
from src.infrastructure.database.models.collection import CollectionModel


class SQLAlchemyCollectionRepository(ICollectionRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, collection_id: UUID) -> CollectionEntity | None:
        result = await self._session.execute(select(CollectionModel).where(CollectionModel.id == collection_id))
        model = result.scalar_one_or_none()
        return self._to_entity(model) if model else None

    async def get_by_user_id(self, user_id: UUID, *, limit: int = 100, offset: int = 0) -> list[CollectionEntity]:
        result = await self._session.execute(
            select(CollectionModel)
            .where(CollectionModel.user_id == user_id)
            .order_by(CollectionModel.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return [self._to_entity(model) for model in result.scalars().all()]

    async def create(self, collection: CollectionEntity) -> None:
        self._session.add(self._to_model(collection))

    async def update(self, collection: CollectionEntity) -> None:
        result = await self._session.execute(select(CollectionModel).where(CollectionModel.id == collection.id))
        model = result.scalar_one()
        model.name = collection.name
        model.description = collection.description
        model.color = collection.color
        model.updated_at = collection.updated_at

    async def delete(self, collection_id: UUID) -> None:
        await self._session.execute(delete(CollectionModel).where(CollectionModel.id == collection_id))

    async def count_by_user_id(self, user_id: UUID) -> int:
        result = await self._session.execute(select(func.count()).select_from(CollectionModel).where(CollectionModel.user_id == user_id))
        return result.scalar_one()

    @staticmethod
    def _to_entity(model: CollectionModel) -> CollectionEntity:
        return CollectionEntity(
            id=model.id,
            user_id=model.user_id,
            name=model.name,
            description=model.description,
            color=model.color,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    @staticmethod
    def _to_model(entity: CollectionEntity) -> CollectionModel:
        return CollectionModel(
            id=entity.id,
            user_id=entity.user_id,
            name=entity.name,
            description=entity.description,
            color=entity.color,
            created_at=entity.created_at,
            updated_at=entity.updated_at,
        )
