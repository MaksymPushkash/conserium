from src.collections.access import normalize_member_role
from src.collections.schemas import (
    CollectionAuditEventResponse,
    CollectionMemberResponse,
    CollectionResponse,
    CollectionShareResponse,
    PublicAskEventListResponse,
    PublicAskEventResponse,
)
from src.models.collection import CollectionModel
from src.public_shares.schemas import CollectionShareRecord, PublicAskEventRecord
from src.workspaces.schemas import CollectionAuditEventRecord, CollectionMemberRecord


def collection_response(collection: CollectionModel, *, access_role: str) -> CollectionResponse:
    return CollectionResponse(
        id=collection.id,
        user_id=collection.user_id,
        workspace_id=collection.workspace_id,
        access_role=access_role,
        name=collection.name,
        description=collection.description,
        color=collection.color,
        created_at=collection.created_at,
        updated_at=collection.updated_at,
    )


def to_collection_share_response(dto: CollectionShareRecord) -> CollectionShareResponse:
    return CollectionShareResponse(
        id=dto.id,
        collection_id=dto.collection_id,
        slug=dto.slug,
        include_summaries=dto.include_summaries,
        include_notes=dto.include_notes,
        ask_enabled=dto.ask_enabled,
        daily_ask_limit=dto.daily_ask_limit,
        revoked_at=dto.revoked_at,
        created_at=dto.created_at,
        updated_at=dto.updated_at,
    )


def to_public_ask_event_list_response(items: list[PublicAskEventRecord]) -> PublicAskEventListResponse:
    return PublicAskEventListResponse(items=[to_public_ask_event_response(item) for item in items])


def to_public_ask_event_response(dto: PublicAskEventRecord) -> PublicAskEventResponse:
    return PublicAskEventResponse(
        id=dto.id,
        share_slug=dto.share_slug,
        status=dto.status,
        reason=dto.reason,
        query_text=dto.query_text,
        answer_share_slug=dto.answer_share_slug,
        created_at=dto.created_at,
    )


def to_collection_member_response(dto: CollectionMemberRecord) -> CollectionMemberResponse:
    return CollectionMemberResponse(
        id=dto.id,
        collection_id=dto.collection_id,
        user_id=dto.user_id,
        email=dto.email,
        role=normalize_member_role(dto.role),
        invite_status="active" if dto.user_id else "pending",
        invited_by_user_id=dto.invited_by_user_id,
        created_at=dto.created_at,
        updated_at=dto.updated_at,
    )


def to_collection_audit_event_response(dto: CollectionAuditEventRecord) -> CollectionAuditEventResponse:
    return CollectionAuditEventResponse(
        id=dto.id,
        collection_id=dto.collection_id,
        actor_user_id=dto.actor_user_id,
        event_type=dto.event_type,
        metadata=dto.metadata,
        created_at=dto.created_at,
    )


__all__ = [
    "collection_response",
    "to_collection_audit_event_response",
    "to_collection_member_response",
    "to_collection_share_response",
    "to_public_ask_event_list_response",
    "to_public_ask_event_response",
]
