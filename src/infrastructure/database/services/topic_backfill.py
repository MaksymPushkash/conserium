from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from sqlalchemy import exists, select
from sqlalchemy.orm import selectinload

from src.application.services.topics.topic_builder import topic_names_from_tags
from src.infrastructure.database.models.base import document_topics
from src.infrastructure.database.models.document import DocumentModel
from src.infrastructure.database.services.document_topic_sync import SQLAlchemyDocumentTopicSync

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True, slots=True)
class TopicBackfillResult:
    scanned_documents: int
    updated_documents: int


class SQLAlchemyTopicBackfill:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._topic_sync = SQLAlchemyDocumentTopicSync(session)

    async def rebuild_missing_topics(self, *, limit: int) -> TopicBackfillResult:
        documents = await self._documents_without_topics(limit)
        updated_documents = 0
        for document in documents:
            topic_names = topic_names_from_tags([tag.name for tag in document.tags])
            if not topic_names:
                continue
            await self._topic_sync.sync_topics(
                user_id=document.user_id,
                document_id=document.id,
                topic_names=topic_names,
            )
            updated_documents += 1
        return TopicBackfillResult(scanned_documents=len(documents), updated_documents=updated_documents)

    async def _documents_without_topics(self, limit: int) -> list[DocumentModel]:
        document_has_topics = exists().where(document_topics.c.document_id == DocumentModel.id)
        result = await self._session.scalars(
            select(DocumentModel)
            .options(selectinload(DocumentModel.tags))
            .where(~document_has_topics)
            .order_by(DocumentModel.created_at.asc())
            .limit(limit)
        )
        return list(result.all())
