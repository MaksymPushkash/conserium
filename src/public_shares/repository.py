from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import and_, func, select, update
from sqlalchemy.orm import selectinload

from src.documents.status import DocumentStatus
from src.models.answer_share import AnswerShareModel
from src.models.collection_share import CollectionShareModel
from src.models.document import DocumentModel
from src.models.public_ask_event import PublicAskEventModel
from src.models.user import UserModel
from src.public_shares.schemas import (
    AnswerShareRecord,
    AnswerShareSource,
    CollectionShareRecord,
    PublicAskEventRecord,
    PublicCollectionDocument,
    PublicCollectionResult,
)

if TYPE_CHECKING:
    from datetime import datetime
    from uuid import UUID

    from sqlalchemy.ext.asyncio import AsyncSession


class AnswerShareRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @classmethod
    def from_session(cls, session: AsyncSession) -> AnswerShareRepository:
        return cls(session)

    async def get_active_by_slug(self, slug: str) -> AnswerShareRecord | None:
        result = await self._session.execute(
            select(AnswerShareModel).options(selectinload(AnswerShareModel.collection)).where(
                AnswerShareModel.slug == slug,
                AnswerShareModel.revoked_at.is_(None),
            )
        )
        model = result.scalar_one_or_none()
        return self._to_record(model) if model else None

    async def list_by_user_id(self, *, user_id: UUID, limit: int, offset: int) -> list[AnswerShareRecord]:
        result = await self._session.execute(
            select(AnswerShareModel)
            .options(selectinload(AnswerShareModel.collection))
            .where(AnswerShareModel.user_id == user_id)
            .order_by(AnswerShareModel.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return [self._to_record(model) for model in result.scalars().all()]

    async def count_recent_by_public_collection_slug(self, *, slug: str, since: datetime) -> int:
        result = await self._session.execute(
            select(func.count())
            .select_from(AnswerShareModel)
            .where(
                AnswerShareModel.public_collection_slug == slug,
                AnswerShareModel.created_at >= since,
                AnswerShareModel.revoked_at.is_(None),
            )
        )
        return int(result.scalar_one())

    async def revoke_by_slug(self, *, user_id: UUID, slug: str, revoked_at: datetime) -> bool:
        result = await self._session.execute(
            select(AnswerShareModel).where(
                AnswerShareModel.user_id == user_id,
                AnswerShareModel.slug == slug,
                AnswerShareModel.revoked_at.is_(None),
            )
        )
        model = result.scalar_one_or_none()
        if model is None:
            return False
        model.revoked_at = revoked_at
        await self._session.flush()
        return True

    async def create(
        self,
        *,
        id: UUID,
        slug: str,
        user_id: UUID,
        collection_id: UUID | None,
        conversation_id: UUID | None,
        public_collection_slug: str | None,
        query_text: str,
        answer_text: str,
        sources: list[AnswerShareSource],
    ) -> AnswerShareRecord:
        model = AnswerShareModel(
            id=id,
            slug=slug,
            user_id=user_id,
            collection_id=collection_id,
            conversation_id=conversation_id,
            public_collection_slug=public_collection_slug,
            query_text=query_text,
            answer_text=answer_text,
            sources=[_source_to_payload(source) for source in sources],
        )
        self._session.add(model)
        await self._session.flush()
        await self._session.refresh(model)
        return self._to_record(model)

    @staticmethod
    def _to_record(model: AnswerShareModel) -> AnswerShareRecord:
        return AnswerShareRecord(
            id=model.id,
            slug=model.slug,
            user_id=model.user_id,
            collection_id=model.collection_id,
            collection_name=model.collection.name if model.collection else None,
            conversation_id=model.conversation_id,
            public_collection_slug=model.public_collection_slug,
            query_text=model.query_text,
            answer_text=model.answer_text,
            sources=[_source_from_payload(item) for item in model.sources],
            revoked_at=model.revoked_at,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )


class CollectionShareRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @classmethod
    def from_session(cls, session: AsyncSession) -> CollectionShareRepository:
        return cls(session)

    async def get_active_by_collection_id(self, *, user_id: UUID, collection_id: UUID) -> CollectionShareRecord | None:
        result = await self._session.execute(
            select(CollectionShareModel).where(
                CollectionShareModel.user_id == user_id,
                CollectionShareModel.collection_id == collection_id,
                CollectionShareModel.revoked_at.is_(None),
            )
        )
        model = result.scalar_one_or_none()
        return self._to_share_record(model) if model else None

    async def get_active_by_slug(self, slug: str) -> CollectionShareRecord | None:
        result = await self._session.execute(
            select(CollectionShareModel).where(
                CollectionShareModel.slug == slug,
                CollectionShareModel.revoked_at.is_(None),
            )
        )
        model = result.scalar_one_or_none()
        return self._to_share_record(model) if model else None

    async def lock_public_ask_scope(self, *, owner_user_id: UUID, share_slug: str) -> CollectionShareRecord | None:
        await self._session.execute(select(UserModel.id).where(UserModel.id == owner_user_id).with_for_update())
        result = await self._session.execute(
            select(CollectionShareModel)
            .where(
                CollectionShareModel.slug == share_slug,
                CollectionShareModel.user_id == owner_user_id,
                CollectionShareModel.revoked_at.is_(None),
            )
            .with_for_update()
        )
        model = result.scalar_one_or_none()
        return self._to_share_record(model) if model else None

    async def create(
        self,
        *,
        id: UUID,
        collection_id: UUID,
        user_id: UUID,
        slug: str,
        include_summaries: bool,
        include_notes: bool,
    ) -> CollectionShareRecord:
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
        return self._to_share_record(model)

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

    async def update_public_ask_settings(
        self,
        *,
        user_id: UUID,
        collection_id: UUID,
        ask_enabled: bool | None,
        daily_ask_limit: int | None,
    ) -> CollectionShareRecord | None:
        result = await self._session.execute(
            select(CollectionShareModel).where(
                CollectionShareModel.user_id == user_id,
                CollectionShareModel.collection_id == collection_id,
                CollectionShareModel.revoked_at.is_(None),
            )
        )
        share = result.scalar_one_or_none()
        if share is None:
            return None
        if ask_enabled is not None:
            share.ask_enabled = ask_enabled
        if daily_ask_limit is not None:
            share.daily_ask_limit = daily_ask_limit
        await self._session.flush()
        return self._to_share_record(share)

    async def count_public_ask_events_by_share(self, *, share_slug: str, since: datetime) -> int:
        result = await self._session.execute(
            select(func.count())
            .select_from(PublicAskEventModel)
            .where(
                PublicAskEventModel.share_slug == share_slug,
                PublicAskEventModel.status.in_(("reserved", "allowed", "failed")),
                PublicAskEventModel.created_at >= since,
            )
        )
        return int(result.scalar_one())

    async def count_public_ask_events_by_owner(self, *, owner_user_id: UUID, since: datetime) -> int:
        result = await self._session.execute(
            select(func.count())
            .select_from(PublicAskEventModel)
            .where(
                PublicAskEventModel.owner_user_id == owner_user_id,
                PublicAskEventModel.status.in_(("reserved", "allowed", "failed")),
                PublicAskEventModel.created_at >= since,
            )
        )
        return int(result.scalar_one())

    async def record_public_ask_event(
        self,
        *,
        id: UUID,
        share_slug: str,
        collection_share_id: UUID | None,
        owner_user_id: UUID,
        client_key: str,
        status: str,
        reason: str | None,
        query_text: str,
        answer_share_slug: str | None,
    ) -> None:
        self._session.add(
            PublicAskEventModel(
                id=id,
                share_slug=share_slug,
                collection_share_id=collection_share_id,
                owner_user_id=owner_user_id,
                client_key=client_key,
                status=status,
                reason=reason,
                query_text=query_text,
                answer_share_slug=answer_share_slug,
            )
        )
        await self._session.flush()

    async def update_public_ask_event(
        self,
        *,
        event_id: UUID,
        status: str,
        reason: str | None,
        answer_share_slug: str | None = None,
    ) -> None:
        await self._session.execute(
            update(PublicAskEventModel)
            .where(PublicAskEventModel.id == event_id)
            .values(status=status, reason=reason, answer_share_slug=answer_share_slug)
        )
        await self._session.flush()

    async def list_public_ask_events(
        self,
        *,
        user_id: UUID,
        collection_id: UUID,
        limit: int,
        offset: int,
    ) -> list[PublicAskEventRecord]:
        share_result = await self._session.execute(
            select(CollectionShareModel).where(
                CollectionShareModel.user_id == user_id,
                CollectionShareModel.collection_id == collection_id,
                CollectionShareModel.revoked_at.is_(None),
            )
        )
        share = share_result.scalar_one_or_none()
        if share is None:
            return []
        result = await self._session.execute(
            select(PublicAskEventModel)
            .where(
                PublicAskEventModel.owner_user_id == user_id,
                PublicAskEventModel.collection_share_id == share.id,
            )
            .order_by(PublicAskEventModel.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return [
            PublicAskEventRecord(
                id=model.id,
                share_slug=model.share_slug,
                status=model.status,
                reason=model.reason,
                query_text=model.query_text,
                answer_share_slug=model.answer_share_slug,
                created_at=model.created_at,
            )
            for model in result.scalars().all()
        ]

    async def get_public_collection(self, slug: str) -> PublicCollectionResult | None:
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
            .options(selectinload(DocumentModel.tag_models))
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
            PublicCollectionDocument(
                id=document.id,
                title=document.title,
                type=document.type,
                status=document.status,
                source_url=document.source_url,
                summary=document.summary if share.include_summaries else None,
                word_count=document.word_count,
                language=document.language,
                tags=document.tags,
                created_at=document.created_at,
                updated_at=document.updated_at,
            )
            for document in document_result.scalars().all()
        ]
        collection = share.collection
        return PublicCollectionResult(
            id=collection.id,
            name=collection.name,
            description=collection.description,
            color=collection.color,
            documents=documents,
            created_at=collection.created_at,
            updated_at=collection.updated_at,
        )

    @staticmethod
    def _to_share_record(model: CollectionShareModel) -> CollectionShareRecord:
        return CollectionShareRecord(
            id=model.id,
            collection_id=model.collection_id,
            user_id=model.user_id,
            slug=model.slug,
            include_summaries=model.include_summaries,
            include_notes=model.include_notes,
            ask_enabled=model.ask_enabled,
            daily_ask_limit=model.daily_ask_limit,
            revoked_at=model.revoked_at,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )


def _source_to_payload(source: AnswerShareSource) -> dict[str, Any]:
    return {
        "chunk_id": str(source.chunk_id),
        "document_id": str(source.document_id),
        "document_title": source.document_title,
        "content": source.content,
        "page_number": source.page_number,
        "chunk_index": source.chunk_index,
        "citation": source.citation,
        "used_in_answer": source.used_in_answer,
    }


def _source_from_payload(payload: dict[str, Any]) -> AnswerShareSource:
    return AnswerShareSource(
        chunk_id=uuid.UUID(str(payload["chunk_id"])),
        document_id=uuid.UUID(str(payload["document_id"])),
        document_title=payload.get("document_title"),
        content=str(payload.get("content", "")),
        page_number=payload.get("page_number"),
        chunk_index=int(payload.get("chunk_index", 0)),
        citation=str(payload.get("citation", "")),
        used_in_answer=bool(payload.get("used_in_answer", False)),
    )


__all__ = [
    "AnswerShareRepository",
    "CollectionShareRepository",
]
