from __future__ import annotations

import uuid
from collections import Counter
from typing import TYPE_CHECKING

from src.application.dtos.collection_dtos import (
    CollectionDTO,
    CollectionListDTO,
    CollectionWorkspaceComparisonDTO,
    CollectionWorkspaceDocumentDTO,
    CollectionWorkspaceDraftDTO,
    CollectionWorkspaceDTO,
    CollectionWorkspaceGapDTO,
    CollectionWorkspaceQuestionDTO,
    CollectionWorkspaceStatsDTO,
    CollectionWorkspaceTopicDTO,
    CreateCollectionDTO,
    DeleteCollectionDTO,
    ListCollectionsDTO,
    UpdateCollectionDTO,
)
from src.application.use_cases.documents.base import document_to_dto
from src.application.use_cases.knowledge_gaps import collection_topic_gaps
from src.domain.entities.collection_entity import CollectionEntity
from src.domain.exceptions import ResourceNotFoundException
from src.domain.value_objects.document_status import DocumentStatus

if TYPE_CHECKING:
    from datetime import datetime
    from uuid import UUID

    from src.application.ports.persistence.document_activity_repository import DocumentActivitySummary
    from src.application.ports.persistence.unit_of_work import IUnitOfWork
    from src.domain.entities.document_entity import DocumentEntity


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


class GetCollectionWorkspaceUseCase:
    def __init__(self, uow: IUnitOfWork) -> None:
        self._uow = uow

    async def __call__(self, *, user_id: UUID, collection_id: UUID) -> CollectionWorkspaceDTO:
        async with self._uow:
            collection = await self._uow.collection_repo.get_by_id(collection_id)
            if collection is None or collection.user_id != user_id:
                raise ResourceNotFoundException("collection not found")
            topic_documents, status_counts = await self._uow.document_repo.get_collection_documents_with_status_counts(
                user_id,
                collection_id=collection_id,
                limit=200,
            )
            documents = topic_documents[:12]
            activity = await self._uow.document_activity_repo.summarize_by_document_ids(
                user_id=user_id,
                document_ids=[document.id for document in documents],
            )
            total_documents = sum(status_counts.values())
            ready_documents = status_counts.get(DocumentStatus.READY, 0)
            failed_documents = status_counts.get(DocumentStatus.FAILED, 0)
            recent_activity = await self._uow.collection_workspace_repo.get_recent_activity(
                user_id=user_id,
                collection_id=collection_id,
                limit=5,
            )
            recent_questions = recent_activity.questions
            recent_drafts = recent_activity.drafts
            recent_comparisons = recent_activity.comparisons

        topics = workspace_topics(topic_documents)
        ready_topic_documents = [document for document in topic_documents if document.status == DocumentStatus.READY]
        knowledge_gaps = collection_topic_gaps(ready_topic_documents, collection_id=collection_id)
        operational_gaps = workspace_gaps(
            total_documents=total_documents,
            ready_documents=ready_documents,
            failed_documents=failed_documents,
            topic_count=len(topics),
        )
        return CollectionWorkspaceDTO(
            collection=_collection_to_dto(collection),
            stats=CollectionWorkspaceStatsDTO(
                total_documents=total_documents,
                ready_documents=ready_documents,
                processing_documents=max(total_documents - ready_documents - failed_documents, 0),
                failed_documents=failed_documents,
                topic_count=len(topics),
                recent_question_count=len(recent_questions),
            ),
            documents=[
                workspace_document(document, activity.get(document.id))
                for document in documents
            ],
            topics=topics[:8],
            gaps=operational_gaps + [
                CollectionWorkspaceGapDTO(
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
                CollectionWorkspaceQuestionDTO(
                    query_text=record.query_text,
                    answer_preview=preview_text(record.answer_text),
                    result_count=record.result_count,
                    created_at=record.created_at,
                )
                for record in recent_questions
            ],
            recent_drafts=[
                CollectionWorkspaceDraftDTO(
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
                for draft in recent_drafts
                if draft.created_at is not None
            ],
            recent_comparisons=[
                CollectionWorkspaceComparisonDTO(
                    id=comparison.id,
                    left_title=comparison.left_title,
                    right_title=comparison.right_title,
                    summary=comparison.summary,
                    dimensions=comparison.dimensions,
                    created_at=comparison.created_at,
                )
                for comparison in recent_comparisons
            ],
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


def workspace_document(document: DocumentEntity, activity: DocumentActivitySummary | None) -> CollectionWorkspaceDocumentDTO:
    dto = document_to_dto(document, activity)
    return CollectionWorkspaceDocumentDTO(
        id=dto.id,
        title=dto.title,
        type=dto.type.value,
        status=dto.status.value,
        summary=dto.summary,
        tags=dto.tags or [],
        activity_temperature=dto.activity_temperature,
        created_at=dto.created_at,
        updated_at=dto.updated_at,
    )


def workspace_topics(documents: list[DocumentEntity]) -> list[CollectionWorkspaceTopicDTO]:
    counts: Counter[str] = Counter()
    last_seen: dict[str, datetime] = {}
    for document in documents:
        for tag in document.tags or []:
            counts[tag] += 1
            current = last_seen.get(tag)
            if current is None or document.created_at > current:
                last_seen[tag] = document.created_at
    return [
        CollectionWorkspaceTopicDTO(
            name=name,
            document_count=count,
            last_document_at=last_seen[name],
        )
        for name, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    ]


def workspace_gaps(
    *,
    total_documents: int,
    ready_documents: int,
    failed_documents: int,
    topic_count: int,
) -> list[CollectionWorkspaceGapDTO]:
    gaps: list[CollectionWorkspaceGapDTO] = []
    if total_documents == 0:
        gaps.append(CollectionWorkspaceGapDTO("No sources", "Add documents before using collection-scoped retrieval.", "high"))
    if total_documents > 0 and ready_documents == 0:
        gaps.append(CollectionWorkspaceGapDTO("No ready documents", "Sources exist, but none are searchable yet.", "high"))
    if failed_documents:
        gaps.append(CollectionWorkspaceGapDTO("Failed processing", f"{failed_documents} document(s) need retry or replacement.", "medium"))
    if ready_documents > 0 and topic_count == 0:
        gaps.append(CollectionWorkspaceGapDTO("No topic coverage", "Ready documents do not have tags or extracted topics yet.", "medium"))
    if ready_documents < 3 and total_documents > 0:
        gaps.append(CollectionWorkspaceGapDTO("Thin evidence base", "Add at least three ready sources for stronger synthesis.", "low"))
    return gaps


def preview_text(value: str | None) -> str | None:
    if not value:
        return None
    return value[:240]
