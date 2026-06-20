from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from src.models.document import DocumentModel
from src.models.topic import TopicModel

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession


class DocumentTopicSync:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def sync_topics(
        self,
        *,
        user_id: uuid.UUID,
        document_id: uuid.UUID,
        topic_names: list[str],
    ) -> list[str]:
        normalized_names = sorted({name.strip().lower() for name in topic_names if name.strip()})
        document = await self._session.scalar(
            select(DocumentModel)
            .options(selectinload(DocumentModel.topics))
            .where(DocumentModel.id == document_id, DocumentModel.user_id == user_id)
        )
        if document is None:
            raise ValueError(f"Document {document_id} not found for topic sync")

        existing_topics = await self._session.scalars(
            select(TopicModel).where(TopicModel.user_id == user_id, TopicModel.name.in_(normalized_names))
        )
        topics_by_name = {topic.name: topic for topic in existing_topics}

        for name in normalized_names:
            if name not in topics_by_name:
                new_topic = TopicModel(user_id=user_id, name=name)
                self._session.add(new_topic)
                await self._session.flush()
                topics_by_name[name] = new_topic

        document.topics = [topics_by_name[name] for name in normalized_names]
        return [topic.name for topic in document.topics]
