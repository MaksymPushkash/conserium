import secrets
import uuid
from datetime import UTC, datetime
from uuid import UUID

from src.application.dtos.collection_share_dtos import CollectionShareDTO, PublicCollectionDTO
from src.application.dtos.query_dtos import QueryDTO, QueryResultDTO
from src.application.ports.persistence.unit_of_work import IUnitOfWork
from src.application.use_cases.query.query_use_case import QueryUseCase
from src.domain.exceptions import ApplicationStateException, ResourceNotFoundException


class GetCollectionShareUseCase:
    def __init__(self, uow: IUnitOfWork) -> None:
        self._uow = uow

    async def __call__(self, *, user_id: UUID, collection_id: UUID) -> CollectionShareDTO | None:
        async with self._uow:
            collection = await self._uow.collection_repo.get_by_id(collection_id)
            if collection is None or collection.user_id != user_id:
                raise ResourceNotFoundException("collection not found")
            return await self._uow.collection_share_repo.get_active_by_collection_id(
                user_id=user_id,
                collection_id=collection_id,
            )


class CreateCollectionShareUseCase:
    def __init__(self, uow: IUnitOfWork) -> None:
        self._uow = uow

    async def __call__(self, *, user_id: UUID, collection_id: UUID) -> CollectionShareDTO:
        async with self._uow:
            collection = await self._uow.collection_repo.get_by_id(collection_id)
            if collection is None or collection.user_id != user_id:
                raise ResourceNotFoundException("collection not found")

            existing = await self._uow.collection_share_repo.get_active_by_collection_id(
                user_id=user_id,
                collection_id=collection_id,
            )
            if existing is not None:
                return existing

            share = await self._create_share(user_id=user_id, collection_id=collection_id)
            await self._uow.commit()
            return share

    async def _create_share(self, *, user_id: UUID, collection_id: UUID) -> CollectionShareDTO:
        for _ in range(5):
            slug = secrets.token_urlsafe(12)
            if await self._uow.collection_share_repo.get_active_by_slug(slug) is not None:
                continue
            return await self._uow.collection_share_repo.create(
                id=uuid.uuid4(),
                collection_id=collection_id,
                user_id=user_id,
                slug=slug,
                include_summaries=True,
                include_notes=False,
            )
        raise ApplicationStateException("could not create share")


class RevokeCollectionShareUseCase:
    def __init__(self, uow: IUnitOfWork) -> None:
        self._uow = uow

    async def __call__(self, *, user_id: UUID, collection_id: UUID) -> None:
        async with self._uow:
            collection = await self._uow.collection_repo.get_by_id(collection_id)
            if collection is None or collection.user_id != user_id:
                raise ResourceNotFoundException("collection not found")
            await self._uow.collection_share_repo.revoke_by_collection_id(
                user_id=user_id,
                collection_id=collection_id,
                revoked_at=datetime.now(UTC),
            )
            await self._uow.commit()


class GetPublicCollectionUseCase:
    def __init__(self, uow: IUnitOfWork) -> None:
        self._uow = uow

    async def __call__(self, *, slug: str) -> PublicCollectionDTO:
        async with self._uow:
            collection = await self._uow.collection_share_repo.get_public_collection(slug)
        if collection is None:
            raise ResourceNotFoundException("public collection not found")
        return collection


class QueryPublicCollectionUseCase:
    def __init__(self, uow: IUnitOfWork, query_use_case: QueryUseCase) -> None:
        self._uow = uow
        self._query_use_case = query_use_case

    async def __call__(self, *, slug: str, query: str, limit: int = 5) -> QueryResultDTO:
        async with self._uow:
            share = await self._uow.collection_share_repo.get_active_by_slug(slug)
        if share is None:
            raise ResourceNotFoundException("public collection not found")

        return await self._query_use_case(
            QueryDTO(
                user_id=share.user_id,
                query=query,
                collection_id=share.collection_id,
                limit=max(1, min(limit, 8)),
            )
        )
