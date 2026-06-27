import uuid
from uuid import UUID

from src.collections.access import (
    WRITE_ROLES as WRITE_ROLES,
)
from src.collections.access import (
    ensure_collection_owner as ensure_collection_owner,
)
from src.collections.access import (
    ensure_collection_visible as ensure_collection_visible,
)
from src.collections.access import (
    ensure_workspace_visible as ensure_workspace_visible,
)
from src.collections.access import (
    ensure_workspace_write_access as ensure_workspace_write_access,
)
from src.collections.access import (
    normalize_member_role as normalize_member_role,
)
from src.collections.repository import CollectionRepository, CollectionWorkspaceRepository
from src.collections.responses import (
    collection_response,
    to_collection_audit_event_response,
    to_collection_member_response,
    to_collection_share_response,
    to_public_ask_event_list_response,
    to_public_ask_event_response,
)
from src.collections.schemas import (
    CollectionAuditEventListResponse,
    CollectionListResponse,
    CollectionMemberListResponse,
    CollectionMemberResponse,
    CollectionResponse,
    CollectionWorkspaceComparisonResponse,
    CollectionWorkspaceDraftResponse,
    CollectionWorkspaceGapResponse,
    CollectionWorkspaceQuestionResponse,
    CollectionWorkspaceResponse,
    CollectionWorkspaceStatsResponse,
)
from src.collections.shares import CollectionShareService, collection_shares
from src.collections.workspace import (
    preview_text,
    workspace_document,
    workspace_gaps,
    workspace_topics,
)
from src.documents.activity_repository import DocumentActivityRepository
from src.documents.document_repository import DocumentRepository
from src.documents.status import DocumentStatus
from src.kit.exceptions import ResourceNotFoundException
from src.knowledge_gaps.service import collection_topic_gaps
from src.models.collection import CollectionModel
from src.postgres import AsyncSession
from src.users.repository import UserRepository
from src.workspaces.repository import SharedWorkspaceRepository


class CollectionService:
    async def create(
        self,
        session: AsyncSession,
        *,
        user_id: UUID,
        name: str,
        workspace_id: UUID | None,
        description: str | None,
        color: str | None,
    ) -> CollectionResponse:
        owner_user_id = user_id
        if workspace_id is not None:
            workspace = await ensure_workspace_write_access(session, workspace_id=workspace_id, user_id=user_id)
            owner_user_id = workspace.user_id
        collection = CollectionModel.create(
            id=uuid.uuid4(),
            user_id=owner_user_id,
            workspace_id=workspace_id,
            name=name,
            description=description,
            color=color,
        )
        await CollectionRepository.from_session(session).create(collection)
        if workspace_id is not None:
            await SharedWorkspaceRepository.from_session(session).create_workspace_audit_event(
                workspace_id=workspace_id,
                actor_user_id=user_id,
                event_type="collection_created",
                metadata={"collection_id": str(collection.id), "name": collection.name},
            )
        await session.flush()
        return collection_response(collection, access_role="owner" if collection.user_id == user_id else "editor")

    async def list(
        self,
        session: AsyncSession,
        *,
        user_id: UUID,
        limit: int,
        offset: int,
        workspace_id: UUID | None,
    ) -> CollectionListResponse:
        collection_repository = CollectionRepository.from_session(session)
        if workspace_id is None:
            collections = await collection_repository.get_visible_by_user_id(user_id, limit=limit, offset=offset)
            total = await collection_repository.count_visible_by_user_id(user_id)
        else:
            await ensure_workspace_visible(session, workspace_id=workspace_id, user_id=user_id)
            collections = await collection_repository.get_visible_by_workspace_id(user_id, workspace_id, limit=limit, offset=offset)
            total = await collection_repository.count_visible_by_workspace_id(user_id, workspace_id)
        items = [
            collection_response(
                collection,
                access_role=await ensure_collection_visible(session, collection_id=collection.id, user_id=user_id),
            )
            for collection in collections
        ]
        return CollectionListResponse(items=items, total=total, limit=limit, offset=offset)

    async def update(
        self,
        session: AsyncSession,
        *,
        user_id: UUID,
        collection_id: UUID,
        name: str,
        description: str | None,
        color: str | None,
    ) -> CollectionResponse:
        repository = CollectionRepository.from_session(session)
        collection = await repository.get_by_id(collection_id)
        if collection is None or collection.user_id != user_id:
            raise ResourceNotFoundException("collection not found")
        collection.update_details(name=name, description=description, color=color)
        await repository.update(collection)
        await session.flush()
        return collection_response(collection, access_role="owner")

    async def delete(self, session: AsyncSession, *, user_id: UUID, collection_id: UUID) -> None:
        repository = CollectionRepository.from_session(session)
        collection = await repository.get_by_id(collection_id)
        if collection is None or collection.user_id != user_id:
            raise ResourceNotFoundException("collection not found")
        await repository.delete(collection_id)
        await session.flush()

    async def list_members(self, session: AsyncSession, *, collection_id: UUID, user_id: UUID) -> CollectionMemberListResponse:
        await ensure_collection_visible(session, collection_id=collection_id, user_id=user_id)
        members = await SharedWorkspaceRepository.from_session(session).list_members(collection_id=collection_id)
        return CollectionMemberListResponse(items=[to_collection_member_response(member) for member in members])

    async def invite_member(
        self,
        session: AsyncSession,
        *,
        collection_id: UUID,
        actor_user_id: UUID,
        email: str,
        role: str,
    ) -> CollectionMemberResponse:
        role = normalize_member_role(role)
        email = email.strip().lower()
        if "@" not in email:
            from src.kit.exceptions import ValidationException

            raise ValidationException("valid member email required")
        await ensure_collection_owner(session, collection_id=collection_id, user_id=actor_user_id)
        user = await UserRepository.from_session(session).get_by_email(email)
        if user is not None and user.id == actor_user_id:
            from src.kit.exceptions import ValidationException

            raise ValidationException("owner is already a collection member")
        repository = SharedWorkspaceRepository.from_session(session)
        member = await repository.upsert_member(
            collection_id=collection_id,
            email=email,
            role=role,
            invited_by_user_id=actor_user_id,
            user_id=user.id if user else None,
        )
        await repository.create_audit_event(
            collection_id=collection_id,
            actor_user_id=actor_user_id,
            event_type="member_invited",
            metadata={"email": email, "role": role},
        )
        await session.flush()
        return to_collection_member_response(member)

    async def update_member_role(
        self,
        session: AsyncSession,
        *,
        collection_id: UUID,
        member_id: UUID,
        actor_user_id: UUID,
        role: str,
    ) -> CollectionMemberResponse:
        role = normalize_member_role(role)
        await ensure_collection_owner(session, collection_id=collection_id, user_id=actor_user_id)
        repository = SharedWorkspaceRepository.from_session(session)
        existing = await repository.get_member(collection_id=collection_id, member_id=member_id)
        if existing is None:
            raise ResourceNotFoundException("collection member not found")
        member = await repository.update_member_role(member_id=member_id, role=role)
        if member is None:
            raise ResourceNotFoundException("collection member not found")
        await repository.create_audit_event(
            collection_id=collection_id,
            actor_user_id=actor_user_id,
            event_type="member_role_updated",
            metadata={"email": existing.email, "previous_role": existing.role, "role": role},
        )
        await session.flush()
        return to_collection_member_response(member)

    async def remove_member(self, session: AsyncSession, *, collection_id: UUID, member_id: UUID, actor_user_id: UUID) -> None:
        await ensure_collection_owner(session, collection_id=collection_id, user_id=actor_user_id)
        repository = SharedWorkspaceRepository.from_session(session)
        existing = await repository.get_member(collection_id=collection_id, member_id=member_id)
        if existing is None:
            raise ResourceNotFoundException("collection member not found")
        await repository.remove_member(member_id=member_id)
        await repository.create_audit_event(
            collection_id=collection_id,
            actor_user_id=actor_user_id,
            event_type="member_removed",
            metadata={"email": existing.email, "role": existing.role},
        )
        await session.flush()

    async def list_audit_events(
        self,
        session: AsyncSession,
        *,
        collection_id: UUID,
        user_id: UUID,
        limit: int,
        offset: int,
    ) -> CollectionAuditEventListResponse:
        await ensure_collection_visible(session, collection_id=collection_id, user_id=user_id)
        events, total = await SharedWorkspaceRepository.from_session(session).list_audit_events(
            collection_id=collection_id,
            limit=limit,
            offset=offset,
        )
        return CollectionAuditEventListResponse(
            items=[to_collection_audit_event_response(event) for event in events],
            total=total,
            limit=limit,
            offset=offset,
        )

    async def workspace(self, session: AsyncSession, *, collection_id: UUID, user_id: UUID) -> CollectionWorkspaceResponse:
        collection = await CollectionRepository.from_session(session).get_by_id(collection_id)
        if collection is None:
            raise ResourceNotFoundException("collection not found")
        access_role = await ensure_collection_visible(session, collection_id=collection_id, user_id=user_id)
        document_owner_id = collection.user_id if collection.workspace_id is not None else user_id
        document_repository = DocumentRepository.from_session(session)
        topic_documents, status_counts = await document_repository.get_collection_documents_with_status_counts(
            document_owner_id,
            collection_id=collection_id,
            limit=200,
        )
        documents = topic_documents[:12]
        activity = await DocumentActivityRepository.from_session(session).summarize_by_document_ids(
            user_id=document_owner_id,
            document_ids=[document.id for document in documents],
        )
        total_documents = sum(status_counts.values())
        ready_documents = status_counts.get(DocumentStatus.READY, 0)
        failed_documents = status_counts.get(DocumentStatus.FAILED, 0)
        recent_activity = await CollectionWorkspaceRepository.from_session(session).get_recent_activity(
            user_id=document_owner_id,
            collection_id=collection_id,
            limit=5,
        )

        topics = workspace_topics(topic_documents)
        ready_topic_documents = [document for document in topic_documents if document.status == DocumentStatus.READY]
        knowledge_gaps = collection_topic_gaps(ready_topic_documents, collection_id=collection_id)
        operational_gaps = workspace_gaps(
            total_documents=total_documents,
            ready_documents=ready_documents,
            failed_documents=failed_documents,
            topic_count=len(topics),
        )
        return CollectionWorkspaceResponse(
                collection=collection_response(collection, access_role=access_role),
                stats=CollectionWorkspaceStatsResponse(
                    total_documents=total_documents,
                    ready_documents=ready_documents,
                    processing_documents=max(total_documents - ready_documents - failed_documents, 0),
                    failed_documents=failed_documents,
                    topic_count=len(topics),
                    recent_question_count=len(recent_activity.questions),
                ),
                documents=[
                    workspace_document(document, activity.get(document.id))
                    for document in documents
                ],
                topics=topics[:8],
                gaps=operational_gaps
                + [
                    CollectionWorkspaceGapResponse(
                        title=f"{gap.topic} coverage",
                        reason=gap.why_detected,
                        severity=gap.severity,
                        id=gap.id,
                        topic=gap.topic,
                        coverage_ratio=gap.coverage_ratio,
                        missing_source_types=gap.missing_source_types,
                        suggested_actions=gap.suggested_actions,
                    )
                    for gap in knowledge_gaps[:5]
                ],
                recent_questions=[
                    CollectionWorkspaceQuestionResponse(
                        query_text=record.query_text,
                        answer_preview=preview_text(record.answer_text),
                        result_count=record.result_count,
                        created_at=record.created_at,
                    )
                    for record in recent_activity.questions
                ],
                recent_drafts=[
                    CollectionWorkspaceDraftResponse(
                        id=draft.id,
                        title=draft.title,
                        prompt=draft.prompt,
                        template_id=draft.template_id,
                        scope_type=draft.scope_type,
                        topic=draft.topic,
                        knowledge_gap_id=draft.knowledge_gap_id,
                        version_number=draft.version_number,
                        created_at=draft.created_at,
                        updated_at=draft.updated_at,
                    )
                    for draft in recent_activity.drafts
                    if draft.created_at is not None
                ],
                recent_comparisons=[
                    CollectionWorkspaceComparisonResponse(
                        id=comparison.id,
                        left_title=comparison.left_title,
                        right_title=comparison.right_title,
                        summary=comparison.summary,
                        dimensions=comparison.dimensions,
                        created_at=comparison.created_at,
                    )
                    for comparison in recent_activity.comparisons
                ],
        )


collections = CollectionService()

__all__ = [
    "CollectionService",
    "CollectionShareService",
    "collection_response",
    "collection_shares",
    "collections",
    "to_collection_audit_event_response",
    "to_collection_member_response",
    "to_collection_share_response",
    "to_public_ask_event_list_response",
    "to_public_ask_event_response",
]
