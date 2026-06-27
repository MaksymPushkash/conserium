from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from src.documents.status import DocumentStatus
from src.kit.exceptions import DocumentAccessDeniedException, DocumentNotFoundException, ResourceNotFoundException
from src.review.helpers import (
    build_learning_steps,
    learning_path_response,
    learning_path_title,
    normalize_step_status,
    review_scope_collection_id,
    review_scope_type,
    update_step_status,
)
from src.review.repository import LearningPathRecord
from src.review.schemas import LearningPathListResponse, LearningPathResponse

if TYPE_CHECKING:
    from uuid import UUID

    from src.documents.document_repository import DocumentRepository
    from src.models.document import DocumentModel
    from src.postgres import AsyncSession
    from src.review.repository import LearningPathRepository
    from src.topics.repository import TopicRepository


class LearningPathGenerator:
    def __init__(
        self,
        session: AsyncSession,
        document_repo: DocumentRepository,
        topic_repo: TopicRepository,
        learning_path_repo: LearningPathRepository,
    ) -> None:
        self._session = session
        self._document_repo = document_repo
        self._topic_repo = topic_repo
        self._learning_path_repo = learning_path_repo

    async def __call__(
        self,
        *,
        user_id: UUID,
        document_id: UUID | None = None,
        collection_id: UUID | None = None,
        topic: str | None = None,
        limit: int = 6,
    ) -> LearningPathResponse:
        documents = await self._load_documents(
            user_id=user_id,
            document_id=document_id,
            collection_id=collection_id,
            topic=topic,
            limit=limit,
        )
        if not documents:
            raise DocumentNotFoundException("no ready documents found for learning path")
        source_document = documents[0]
        record = LearningPathRecord(
            id=uuid.uuid4(),
            user_id=user_id,
            scope_type=review_scope_type(document_id=document_id, collection_id=collection_id, topic=topic),
            collection_id=review_scope_collection_id(
                document_id=document_id,
                collection_id=collection_id,
                document=source_document,
            ),
            topic=topic.strip() if topic and topic.strip() else None,
            source_document_id=source_document.id,
            title=learning_path_title(topic=topic, collection_id=collection_id, source_document=source_document),
            steps=build_learning_steps(documents, limit=limit),
            created_at=datetime.now(UTC),
            updated_at=None,
        )
        created = await self._learning_path_repo.create(record)
        await self._session.flush()
        return learning_path_response(created)

    async def _load_documents(
        self,
        *,
        user_id: UUID,
        document_id: UUID | None,
        collection_id: UUID | None,
        topic: str | None,
        limit: int,
    ) -> list[DocumentModel]:
        if document_id is not None:
            document = await self._document_repo.get_by_id(document_id)
            if document is None:
                raise DocumentNotFoundException("document not found")
            if document.user_id != user_id:
                raise DocumentAccessDeniedException("document access denied")
            if document.status != DocumentStatus.READY:
                return []
            return [document]
        if topic:
            detail = await self._topic_repo.get_detail_by_name(
                user_id,
                name=topic,
                document_limit=max(1, min(limit * 3, 60)),
            )
            if detail is None:
                return []
            documents: list[DocumentModel] = []
            for topic_document in detail.documents:
                document = await self._document_repo.get_by_id(topic_document.id)
                if document and document.user_id == user_id and document.status == DocumentStatus.READY:
                    documents.append(document)
            return documents
        return await self._document_repo.get_by_user_id(
            user_id,
            limit=max(1, min(limit * 3, 60)),
            collection_id=collection_id,
            status=DocumentStatus.READY,
        )


class LearningPathStepUpdater:
    def __init__(self, session: AsyncSession, learning_path_repo: LearningPathRepository) -> None:
        self._session = session
        self._learning_path_repo = learning_path_repo

    async def __call__(self, *, user_id: UUID, path_id: UUID, step_id: str, status: str) -> LearningPathResponse:
        normalized_status = normalize_step_status(status)
        record = await self._learning_path_repo.get_by_id(path_id)
        if record is None or record.user_id != user_id:
            raise ResourceNotFoundException("learning path not found")
        steps = update_step_status(record.steps, step_id=step_id, status=normalized_status)
        updated = await self._learning_path_repo.update_steps(record.id, steps)
        await self._session.flush()
        return learning_path_response(updated)


class LearningPathRegenerator:
    def __init__(
        self,
        generate_learning_path: LearningPathGenerator,
        learning_path_repo: LearningPathRepository,
    ) -> None:
        self._generate_learning_path = generate_learning_path
        self._learning_path_repo = learning_path_repo

    async def __call__(self, *, user_id: UUID, path_id: UUID, limit: int = 6) -> LearningPathResponse:
        record = await self._learning_path_repo.get_by_id(path_id)
        if record is None or record.user_id != user_id:
            raise ResourceNotFoundException("learning path not found")
        return await self._generate_learning_path(
            user_id=user_id,
            document_id=record.source_document_id if record.scope_type == "document" else None,
            collection_id=record.collection_id if record.scope_type == "collection" else None,
            topic=record.topic if record.scope_type == "topic" else None,
            limit=limit,
        )


async def list_learning_paths(
    learning_path_repo: LearningPathRepository,
    *,
    user_id: UUID,
    limit: int = 10,
) -> LearningPathListResponse:
    items = await learning_path_repo.list_by_user(user_id=user_id, limit=limit)
    return LearningPathListResponse(items=[learning_path_response(item) for item in items], total=len(items), limit=limit)


__all__ = [
    "LearningPathGenerator",
    "LearningPathRegenerator",
    "LearningPathStepUpdater",
    "list_learning_paths",
]
