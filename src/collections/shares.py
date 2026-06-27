import secrets
import uuid
from datetime import UTC, datetime
from uuid import UUID

from src.collections.access import ensure_collection_owner
from src.collections.responses import to_collection_share_response, to_public_ask_event_list_response
from src.collections.schemas import CollectionShareResponse, PublicAskEventListResponse
from src.kit.exceptions import ApplicationStateException, ResourceNotFoundException
from src.postgres import AsyncSession
from src.public_shares.repository import CollectionShareRepository


class CollectionShareService:
    async def get_share(
        self,
        session: AsyncSession,
        *,
        user_id: UUID,
        collection_id: UUID,
    ) -> CollectionShareResponse | None:
        await ensure_collection_owner(session, user_id=user_id, collection_id=collection_id)
        share = await CollectionShareRepository.from_session(session).get_active_by_collection_id(
            user_id=user_id,
            collection_id=collection_id,
        )
        return to_collection_share_response(share) if share is not None else None

    async def create_share(self, session: AsyncSession, *, user_id: UUID, collection_id: UUID) -> CollectionShareResponse:
        await ensure_collection_owner(session, user_id=user_id, collection_id=collection_id)
        repository = CollectionShareRepository.from_session(session)
        existing = await repository.get_active_by_collection_id(user_id=user_id, collection_id=collection_id)
        if existing is not None:
            return to_collection_share_response(existing)
        for _ in range(5):
            slug = secrets.token_urlsafe(12)
            if await repository.get_active_by_slug(slug) is not None:
                continue
            share = await repository.create(
                id=uuid.uuid4(),
                collection_id=collection_id,
                user_id=user_id,
                slug=slug,
                include_summaries=True,
                include_notes=False,
            )
            await session.flush()
            return to_collection_share_response(share)
        raise ApplicationStateException("could not create share")

    async def list_ask_events(
        self,
        session: AsyncSession,
        *,
        user_id: UUID,
        collection_id: UUID,
        limit: int,
        offset: int,
    ) -> PublicAskEventListResponse:
        await ensure_collection_owner(session, user_id=user_id, collection_id=collection_id)
        events = await CollectionShareRepository.from_session(session).list_public_ask_events(
            user_id=user_id,
            collection_id=collection_id,
            limit=max(1, min(limit, 100)),
            offset=max(0, offset),
        )
        return to_public_ask_event_list_response(events)

    async def update_share_settings(
        self,
        session: AsyncSession,
        *,
        user_id: UUID,
        collection_id: UUID,
        ask_enabled: bool | None,
        daily_ask_limit: int | None,
    ) -> CollectionShareResponse:
        await ensure_collection_owner(session, user_id=user_id, collection_id=collection_id)
        share = await CollectionShareRepository.from_session(session).update_public_ask_settings(
            user_id=user_id,
            collection_id=collection_id,
            ask_enabled=ask_enabled,
            daily_ask_limit=daily_ask_limit,
        )
        if share is None:
            raise ResourceNotFoundException("collection share not found")
        await session.flush()
        return to_collection_share_response(share)

    async def revoke_share(self, session: AsyncSession, *, user_id: UUID, collection_id: UUID) -> None:
        await ensure_collection_owner(session, user_id=user_id, collection_id=collection_id)
        await CollectionShareRepository.from_session(session).revoke_by_collection_id(
            user_id=user_id,
            collection_id=collection_id,
            revoked_at=datetime.now(UTC),
        )
        await session.flush()


collection_shares = CollectionShareService()


__all__ = ["CollectionShareService", "collection_shares"]
