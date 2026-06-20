from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from sqlalchemy import exists, select
from sqlalchemy.orm import selectinload

from src.documents.topic_sync import DocumentTopicSync
from src.models.base import document_topics
from src.models.document import DocumentModel
from src.topics.services.topic_builder import topic_names_from_tags

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True, slots=True)
class TopicBackfillResult:
    scanned_documents: int
    updated_documents: int


class TopicBackfill:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._topic_sync = DocumentTopicSync(session)

    async def rebuild_missing_topics(self, *, limit: int) -> TopicBackfillResult:
        documents = await self._documents_without_topics(limit)
        updated_documents = 0
        for document in documents:
            topic_names = topic_names_from_tags(document.tags)
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
            .options(selectinload(DocumentModel.tag_models))
            .where(~document_has_topics)
            .order_by(DocumentModel.created_at.asc())
            .limit(limit)
        )
        return list(result.all())
