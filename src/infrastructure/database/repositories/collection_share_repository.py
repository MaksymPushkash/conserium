from datetime import datetime
from uuid import UUID

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.application.dtos.collection_share_dtos import (
    CollectionShareDTO,
    PublicCollectionDocumentDTO,
    PublicCollectionDTO,
)
from src.application.ports.persistence.collection_share_repository import ICollectionShareRepository
from src.domain.value_objects.document_status import DocumentStatus
from src.infrastructure.database.models.collection_share import CollectionShareModel
from src.infrastructure.database.models.document import DocumentModel


class SQLAlchemyCollectionShareRepository(ICollectionShareRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_active_by_collection_id(self, *, user_id: UUID, collection_id: UUID) -> CollectionShareDTO | None:
        result = await self._session.execute(
            select(CollectionShareModel).where(
                CollectionShareModel.user_id == user_id,
                CollectionShareModel.collection_id == collection_id,
                CollectionShareModel.revoked_at.is_(None),
            )
        )
        model = result.scalar_one_or_none()
        return self._to_share_dto(model) if model else None

    async def get_active_by_slug(self, slug: str) -> CollectionShareDTO | None:
        result = await self._session.execute(
            select(CollectionShareModel).where(
                CollectionShareModel.slug == slug,
                CollectionShareModel.revoked_at.is_(None),
            )
        )
        model = result.scalar_one_or_none()
        return self._to_share_dto(model) if model else None

    async def create(
        self,
        *,
        id: UUID,
        collection_id: UUID,
        user_id: UUID,
        slug: str,
        include_summaries: bool,
        include_notes: bool,
    ) -> CollectionShareDTO:
        model = CollectionShareModel(
            id=id,
            collection_id=collection_id,
            user_id=user_id,
            slug=slug,
            include_summaries=include_summaries,
            include_notes=include_notes,
        )
        self._session.add(model)
        await self._session.flush()
        await self._session.refresh(model)
        return self._to_share_dto(model)

    async def revoke_by_collection_id(self, *, user_id: UUID, collection_id: UUID, revoked_at: datetime) -> bool:
        result = await self._session.execute(
            select(CollectionShareModel).where(
                CollectionShareModel.user_id == user_id,
                CollectionShareModel.collection_id == collection_id,
                CollectionShareModel.revoked_at.is_(None),
            )
        )
        share = result.scalar_one_or_none()
        if share is None:
            return False
        share.revoked_at = revoked_at
        return True

    async def get_public_collection(self, slug: str) -> PublicCollectionDTO | None:
        share_result = await self._session.execute(
            select(CollectionShareModel)
            .options(selectinload(CollectionShareModel.collection))
            .where(
                CollectionShareModel.slug == slug,
                CollectionShareModel.revoked_at.is_(None),
            )
        )
        share = share_result.scalar_one_or_none()
        if share is None:
            return None

        document_result = await self._session.execute(
            select(DocumentModel)
            .options(selectinload(DocumentModel.tags))
            .where(
                and_(
                    DocumentModel.collection_id == share.collection_id,
                    DocumentModel.user_id == share.user_id,
                    DocumentModel.status == DocumentStatus.READY,
                )
            )
            .order_by(DocumentModel.created_at.desc())
            .limit(100)
        )
        documents = [
            PublicCollectionDocumentDTO(
                id=document.id,
                title=document.title,
                type=document.type,
                status=document.status,
                source_url=document.source_url,
                summary=document.summary if share.include_summaries else None,
                word_count=document.word_count,
                language=document.language,
                tags=[tag.name for tag in document.tags],
                created_at=document.created_at,
                updated_at=document.updated_at,
            )
            for document in document_result.scalars().all()
        ]
        collection = share.collection
        return PublicCollectionDTO(
            id=collection.id,
            name=collection.name,
            description=collection.description,
            color=collection.color,
            documents=documents,
            created_at=collection.created_at,
            updated_at=collection.updated_at,
        )

    @staticmethod
    def _to_share_dto(model: CollectionShareModel) -> CollectionShareDTO:
        return CollectionShareDTO(
            id=model.id,
            collection_id=model.collection_id,
            user_id=model.user_id,
            slug=model.slug,
            include_summaries=model.include_summaries,
            include_notes=model.include_notes,
            revoked_at=model.revoked_at,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )
