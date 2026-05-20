import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, cast

import pytest

from src.application.dtos.collection_share_dtos import (
    CollectionShareDTO,
    PublicCollectionDocumentDTO,
    PublicCollectionDTO,
)
from src.application.use_cases.collection_shares import (
    CreateCollectionShareUseCase,
    GetPublicCollectionUseCase,
    RevokeCollectionShareUseCase,
)
from src.domain.entities.collection_entity import CollectionEntity
from src.domain.exceptions import ResourceNotFoundException
from src.domain.value_objects.document_status import DocumentStatus
from src.domain.value_objects.document_type import DocumentType

if TYPE_CHECKING:
    from src.application.ports.persistence.unit_of_work import IUnitOfWork


class _FakeCollectionRepository:
    def __init__(self, collection: CollectionEntity | None) -> None:
        self.collection = collection

    async def get_by_id(self, collection_id: uuid.UUID) -> CollectionEntity | None:
        return self.collection if self.collection and self.collection.id == collection_id else None


class _FakeCollectionShareRepository:
    def __init__(self) -> None:
        self.share: CollectionShareDTO | None = None
        self.public_collection: PublicCollectionDTO | None = None
        self.revoked: tuple[uuid.UUID, uuid.UUID] | None = None

    async def get_active_by_collection_id(
        self,
        *,
        user_id: uuid.UUID,
        collection_id: uuid.UUID,
    ) -> CollectionShareDTO | None:
        if self.share and self.share.user_id == user_id and self.share.collection_id == collection_id:
            return self.share
        return None

    async def get_active_by_slug(self, slug: str) -> CollectionShareDTO | None:
        if self.share and self.share.slug == slug:
            return self.share
        return None

    async def create(
        self,
        *,
        id: uuid.UUID,
        collection_id: uuid.UUID,
        user_id: uuid.UUID,
        slug: str,
        include_summaries: bool,
        include_notes: bool,
    ) -> CollectionShareDTO:
        self.share = CollectionShareDTO(
            id=id,
            collection_id=collection_id,
            user_id=user_id,
            slug=slug,
            include_summaries=include_summaries,
            include_notes=include_notes,
            revoked_at=None,
            created_at=datetime.now(UTC),
            updated_at=None,
        )
        return self.share

    async def revoke_by_collection_id(
        self,
        *,
        user_id: uuid.UUID,
        collection_id: uuid.UUID,
        revoked_at: datetime,
    ) -> bool:
        self.revoked = (user_id, collection_id)
        if self.share:
            self.share = CollectionShareDTO(
                id=self.share.id,
                collection_id=self.share.collection_id,
                user_id=self.share.user_id,
                slug=self.share.slug,
                include_summaries=self.share.include_summaries,
                include_notes=self.share.include_notes,
                revoked_at=revoked_at,
                created_at=self.share.created_at,
                updated_at=self.share.updated_at,
            )
        return True

    async def get_public_collection(self, slug: str) -> PublicCollectionDTO | None:
        if self.share and self.share.slug == slug and self.share.revoked_at is None:
            return self.public_collection
        return None


class _FakeUnitOfWork:
    def __init__(self, collection: CollectionEntity | None) -> None:
        self.collection_repo = _FakeCollectionRepository(collection)
        self.collection_share_repo = _FakeCollectionShareRepository()
        self.committed = False

    async def __aenter__(self) -> "_FakeUnitOfWork":
        return self

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None

    async def commit(self) -> None:
        self.committed = True

    async def rollback(self) -> None:
        return None


@pytest.mark.asyncio
async def test_create_collection_share_returns_active_share() -> None:
    user_id = uuid.uuid4()
    collection = _make_collection(user_id)
    uow = _FakeUnitOfWork(collection)
    use_case = CreateCollectionShareUseCase(cast("IUnitOfWork", uow))

    share = await use_case(user_id=user_id, collection_id=collection.id)

    assert share.collection_id == collection.id
    assert share.user_id == user_id
    assert share.include_summaries is True
    assert share.include_notes is False
    assert uow.committed is True


@pytest.mark.asyncio
async def test_create_collection_share_rejects_non_owner() -> None:
    collection = _make_collection(uuid.uuid4())
    use_case = CreateCollectionShareUseCase(cast("IUnitOfWork", _FakeUnitOfWork(collection)))

    with pytest.raises(ResourceNotFoundException):
        await use_case(user_id=uuid.uuid4(), collection_id=collection.id)


@pytest.mark.asyncio
async def test_revoke_collection_share_marks_active_share_revoked() -> None:
    user_id = uuid.uuid4()
    collection = _make_collection(user_id)
    uow = _FakeUnitOfWork(collection)
    create_use_case = CreateCollectionShareUseCase(cast("IUnitOfWork", uow))
    revoke_use_case = RevokeCollectionShareUseCase(cast("IUnitOfWork", uow))

    await create_use_case(user_id=user_id, collection_id=collection.id)
    await revoke_use_case(user_id=user_id, collection_id=collection.id)

    assert uow.collection_share_repo.revoked == (user_id, collection.id)


@pytest.mark.asyncio
async def test_public_collection_returns_shared_documents() -> None:
    user_id = uuid.uuid4()
    collection = _make_collection(user_id)
    uow = _FakeUnitOfWork(collection)
    share = await CreateCollectionShareUseCase(cast("IUnitOfWork", uow))(user_id=user_id, collection_id=collection.id)
    uow.collection_share_repo.public_collection = PublicCollectionDTO(
        id=collection.id,
        name=collection.name,
        description=collection.description,
        color=collection.color,
        documents=[
            PublicCollectionDocumentDTO(
                id=uuid.uuid4(),
                title="Async Python",
                type=DocumentType.TEXT,
                status=DocumentStatus.READY,
                source_url=None,
                summary="Async summary.",
                word_count=120,
                language="en",
                tags=["python"],
                created_at=datetime.now(UTC),
                updated_at=None,
            )
        ],
        created_at=collection.created_at,
        updated_at=collection.updated_at,
    )

    result = await GetPublicCollectionUseCase(cast("IUnitOfWork", uow))(slug=share.slug)

    assert result.name == "Python"
    assert result.documents[0].summary == "Async summary."


def _make_collection(user_id: uuid.UUID) -> CollectionEntity:
    return CollectionEntity.create(
        id=uuid.uuid4(),
        user_id=user_id,
        name="Python",
        description="Python material",
        color="#ffffff",
    )
