from __future__ import annotations

from typing import TYPE_CHECKING

from src.collections.access import ensure_collection_visible
from src.kit.exceptions import (
    DocumentAccessDeniedException,
    ResourceNotFoundException,
)

if TYPE_CHECKING:
    from uuid import UUID

    from src.collections.repository import CollectionRepository
    from src.models.document import DocumentModel
    from src.postgres import AsyncSession
    from src.workspaces.repository import SharedWorkspaceRepository


class DocumentCollectionAccess:
    def __init__(
        self,
        session: AsyncSession,
        collection_repo: CollectionRepository,
        shared_workspace_repo: SharedWorkspaceRepository,
    ) -> None:
        self._session = session
        self._collection_repo = collection_repo
        self._shared_workspace_repo = shared_workspace_repo

    async def ensure_write(self, *, collection_id: UUID, user_id: UUID) -> None:
        role = await ensure_collection_visible(self._session, collection_id=collection_id, user_id=user_id)
        if role not in {"owner", "editor"}:
            raise ResourceNotFoundException("collection not found")

    async def ensure_visible(self, *, collection_id: UUID, user_id: UUID) -> None:
        await ensure_collection_visible(self._session, collection_id=collection_id, user_id=user_id)

    async def document_owner_id(self, *, collection_id: UUID | None, user_id: UUID) -> UUID:
        if collection_id is None:
            return user_id
        await self.ensure_write(collection_id=collection_id, user_id=user_id)
        collection = await self._collection_repo.get_by_id(collection_id)
        if collection is None:
            raise ResourceNotFoundException("collection not found")
        return collection.user_id if collection.workspace_id is not None else user_id

    async def record_shared_document_event(
        self,
        *,
        collection_id: UUID,
        actor_user_id: UUID,
        document_id: UUID,
        title: str,
    ) -> None:
        collection = await self._collection_repo.get_by_id(collection_id)
        if collection is not None and collection.user_id != actor_user_id:
            await self._shared_workspace_repo.create_audit_event(
                collection_id=collection_id,
                actor_user_id=actor_user_id,
                event_type="shared_ingestion",
                metadata={"document_id": str(document_id), "title": title},
            )


def ensure_document_owner(document: DocumentModel, user_id: object) -> None:
    if document.user_id != user_id:
        raise DocumentAccessDeniedException("document access denied")


async def ensure_collection_owner(
    collection_access: DocumentCollectionAccess,
    collection_id: UUID | None,
    user_id: UUID,
) -> None:
    if collection_id is None:
        return
    await collection_access.ensure_write(collection_id=collection_id, user_id=user_id)


async def collection_document_owner_id(
    collection_access: DocumentCollectionAccess,
    collection_id: UUID | None,
    user_id: UUID,
) -> UUID:
    if collection_id is None:
        return user_id
    return await collection_access.document_owner_id(collection_id=collection_id, user_id=user_id)


async def ensure_document_collection_visible(
    collection_access: DocumentCollectionAccess,
    *,
    collection_id: UUID,
    user_id: UUID,
) -> None:
    await collection_access.ensure_visible(collection_id=collection_id, user_id=user_id)


async def record_shared_document_event(
    collection_access: DocumentCollectionAccess,
    *,
    collection_id: UUID,
    actor_user_id: UUID,
    document_id: UUID,
    title: str,
) -> None:
    await collection_access.record_shared_document_event(
        collection_id=collection_id,
        actor_user_id=actor_user_id,
        document_id=document_id,
        title=title,
    )
