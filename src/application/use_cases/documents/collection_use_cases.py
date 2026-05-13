from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from src.application.dtos.collection_dtos import (
    CollectionDTO,
    CollectionListDTO,
    CreateCollectionDTO,
    DeleteCollectionDTO,
    ListCollectionsDTO,
    UpdateCollectionDTO,
)
from src.domain.entities.collection_entity import CollectionEntity
from src.domain.exceptions import ResourceNotFoundException

if TYPE_CHECKING:
    from src.application.ports.persistence.unit_of_work import IUnitOfWork


class CreateCollectionUseCase:
    def __init__(self, uow: IUnitOfWork) -> None:
        self._uow = uow

    async def __call__(self, dto: CreateCollectionDTO) -> CollectionDTO:
        collection = CollectionEntity.create(
            id=uuid.uuid4(),
            user_id=dto.user_id,
            name=dto.name,
            description=dto.description,
            color=dto.color,
        )
        async with self._uow:
            await self._uow.collection_repo.create(collection)
            await self._uow.commit()
        return _collection_to_dto(collection)


class ListCollectionsUseCase:
    def __init__(self, uow: IUnitOfWork) -> None:
        self._uow = uow

    async def __call__(self, dto: ListCollectionsDTO) -> CollectionListDTO:
        async with self._uow:
            collections = await self._uow.collection_repo.get_by_user_id(dto.user_id, limit=dto.limit, offset=dto.offset)
            total = await self._uow.collection_repo.count_by_user_id(dto.user_id)
        return CollectionListDTO(
            items=[_collection_to_dto(collection) for collection in collections],
            total=total,
            limit=dto.limit,
            offset=dto.offset,
        )


class UpdateCollectionUseCase:
    def __init__(self, uow: IUnitOfWork) -> None:
        self._uow = uow

    async def __call__(self, dto: UpdateCollectionDTO) -> CollectionDTO:
        async with self._uow:
            collection = await self._uow.collection_repo.get_by_id(dto.collection_id)
            if collection is None or collection.user_id != dto.user_id:
                raise ResourceNotFoundException("collection not found")
            collection.update(name=dto.name, description=dto.description, color=dto.color)
            await self._uow.collection_repo.update(collection)
            await self._uow.commit()
        return _collection_to_dto(collection)


class DeleteCollectionUseCase:
    def __init__(self, uow: IUnitOfWork) -> None:
        self._uow = uow

    async def __call__(self, dto: DeleteCollectionDTO) -> None:
        async with self._uow:
            collection = await self._uow.collection_repo.get_by_id(dto.collection_id)
            if collection is None or collection.user_id != dto.user_id:
                raise ResourceNotFoundException("collection not found")
            await self._uow.collection_repo.delete(dto.collection_id)
            await self._uow.commit()


def _collection_to_dto(collection: CollectionEntity) -> CollectionDTO:
    return CollectionDTO(
        id=collection.id,
        user_id=collection.user_id,
        name=collection.name,
        description=collection.description,
        color=collection.color,
        created_at=collection.created_at,
        updated_at=collection.updated_at,
    )
