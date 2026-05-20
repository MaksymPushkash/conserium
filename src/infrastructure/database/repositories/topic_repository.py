from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import distinct, exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.application.ports.persistence.topic_repository import (
    ITopicRepository,
    TopicDetailRecord,
    TopicDocumentRecord,
    TopicRecord,
)
from src.infrastructure.database.models.base import document_tags, document_topics
from src.infrastructure.database.models.document import DocumentModel
from src.infrastructure.database.models.tag import TagModel
from src.infrastructure.database.models.topic import TopicModel


class SQLAlchemyTopicRepository(ITopicRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_by_user_id(self, user_id: UUID, *, limit: int, offset: int) -> list[TopicRecord]:
        topics = await self._merged_topics(user_id)
        topics.sort(key=lambda topic: (-topic.document_count, topic.name))
        return topics[offset : offset + limit]

    async def count_by_user_id(self, user_id: UUID) -> int:
        return len(await self._merged_topics(user_id))

    async def get_detail_by_name(
        self,
        user_id: UUID,
        *,
        name: str,
        document_limit: int,
    ) -> TopicDetailRecord | None:
        topics = await self._merged_topics(user_id)
        topic = next((record for record in topics if record.name == name), None)
        if topic is None:
            return None
        documents = await self._documents_for_topic(user_id=user_id, name=name, limit=document_limit)
        return TopicDetailRecord(topic=topic, documents=documents)

    async def get_details_by_names(
        self,
        user_id: UUID,
        *,
        names: set[str],
        document_limit: int,
    ) -> dict[str, TopicDetailRecord]:
        if not names:
            return {}
        requested_names = {name.casefold(): name for name in names}
        topics = {
            record.name.casefold(): record
            for record in await self._merged_topics(user_id)
            if record.name.casefold() in requested_names
        }
        documents = await self._documents_for_topic_names(
            user_id=user_id,
            names={topic.name for topic in topics.values()},
            limit=document_limit,
        )
        return {
            topic_name: TopicDetailRecord(topic=topic, documents=documents.get(topic.name.casefold(), []))
            for topic_name, topic in topics.items()
        }

    async def _merged_topics(self, user_id: UUID) -> list[TopicRecord]:
        topics: dict[str, TopicRecord] = {}
        for record in await self._stored_topics(user_id):
            topics[record.name] = record
        for record in await self._fallback_tag_topics(user_id):
            current = topics.get(record.name)
            if current is None:
                topics[record.name] = record
            else:
                topics[record.name] = TopicRecord(
                    name=current.name,
                    document_count=current.document_count + record.document_count,
                    last_document_at=max_date(current.last_document_at, record.last_document_at),
                )
        return list(topics.values())

    async def _stored_topics(self, user_id: UUID) -> list[TopicRecord]:
        statement = (
            select(
                TopicModel.name,
                func.count(distinct(DocumentModel.id)).label("document_count"),
                func.max(DocumentModel.created_at).label("last_document_at"),
            )
            .join(document_topics, document_topics.c.topic_id == TopicModel.id)
            .join(DocumentModel, DocumentModel.id == document_topics.c.document_id)
            .where(TopicModel.user_id == user_id)
            .where(DocumentModel.user_id == user_id)
            .group_by(TopicModel.name)
        )
        rows = (await self._session.execute(statement)).all()
        return [
            TopicRecord(
                name=row.name,
                document_count=int(row.document_count),
                last_document_at=row.last_document_at,
            )
            for row in rows
        ]

    async def _fallback_tag_topics(self, user_id: UUID) -> list[TopicRecord]:
        document_has_topics = exists().where(document_topics.c.document_id == DocumentModel.id)
        statement = (
            select(
                TagModel.name,
                func.count(distinct(DocumentModel.id)).label("document_count"),
                func.max(DocumentModel.created_at).label("last_document_at"),
            )
            .join(document_tags, document_tags.c.tag_id == TagModel.id)
            .join(DocumentModel, DocumentModel.id == document_tags.c.document_id)
            .where(TagModel.user_id == user_id)
            .where(DocumentModel.user_id == user_id)
            .where(~document_has_topics)
            .group_by(TagModel.name)
        )
        rows = (await self._session.execute(statement)).all()
        return [
            TopicRecord(
                name=row.name,
                document_count=int(row.document_count),
                last_document_at=row.last_document_at,
            )
            for row in rows
        ]

    async def _documents_for_topic(self, *, user_id: UUID, name: str, limit: int) -> list[TopicDocumentRecord]:
        documents: dict[UUID, TopicDocumentRecord] = {}
        for record in await self._stored_topic_documents(user_id=user_id, name=name, limit=limit):
            documents[record.id] = record
        if len(documents) < limit:
            for record in await self._fallback_tag_documents(user_id=user_id, name=name, limit=limit):
                documents.setdefault(record.id, record)
        ranked = sorted(documents.values(), key=lambda document: document.created_at, reverse=True)
        return ranked[:limit]

    async def _documents_for_topic_names(
        self,
        *,
        user_id: UUID,
        names: set[str],
        limit: int,
    ) -> dict[str, list[TopicDocumentRecord]]:
        documents: dict[str, dict[UUID, TopicDocumentRecord]] = {name.casefold(): {} for name in names}
        for topic_name, records in (await self._stored_topic_documents_by_name(user_id=user_id, names=names)).items():
            for record in records:
                documents.setdefault(topic_name.casefold(), {})[record.id] = record
        fallback_names = {name for name in names if len(documents.get(name.casefold(), {})) < limit}
        for topic_name, records in (await self._fallback_tag_documents_by_name(user_id=user_id, names=fallback_names)).items():
            topic_documents = documents.setdefault(topic_name.casefold(), {})
            for record in records:
                topic_documents.setdefault(record.id, record)
        return {
            topic_name: sorted(topic_documents.values(), key=lambda document: document.created_at, reverse=True)[:limit]
            for topic_name, topic_documents in documents.items()
        }

    async def _stored_topic_documents(self, *, user_id: UUID, name: str, limit: int) -> list[TopicDocumentRecord]:
        statement = (
            select(
                DocumentModel.id,
                DocumentModel.title,
                DocumentModel.type,
                DocumentModel.status,
                DocumentModel.summary,
                DocumentModel.created_at,
            )
            .join(document_topics, document_topics.c.document_id == DocumentModel.id)
            .join(TopicModel, TopicModel.id == document_topics.c.topic_id)
            .where(DocumentModel.user_id == user_id)
            .where(TopicModel.user_id == user_id)
            .where(TopicModel.name == name)
            .order_by(DocumentModel.created_at.desc())
            .limit(limit)
        )
        return [topic_document_record(row) for row in (await self._session.execute(statement)).all()]

    async def _stored_topic_documents_by_name(self, *, user_id: UUID, names: set[str]) -> dict[str, list[TopicDocumentRecord]]:
        if not names:
            return {}
        statement = (
            select(
                TopicModel.name.label("topic_name"),
                DocumentModel.id,
                DocumentModel.title,
                DocumentModel.type,
                DocumentModel.status,
                DocumentModel.summary,
                DocumentModel.created_at,
            )
            .join(document_topics, document_topics.c.document_id == DocumentModel.id)
            .join(TopicModel, TopicModel.id == document_topics.c.topic_id)
            .where(DocumentModel.user_id == user_id)
            .where(TopicModel.user_id == user_id)
            .where(TopicModel.name.in_(names))
            .order_by(TopicModel.name.asc(), DocumentModel.created_at.desc())
        )
        grouped: dict[str, list[TopicDocumentRecord]] = {}
        for row in (await self._session.execute(statement)).all():
            grouped.setdefault(row.topic_name, []).append(topic_document_record(row))
        return grouped

    async def _fallback_tag_documents(self, *, user_id: UUID, name: str, limit: int) -> list[TopicDocumentRecord]:
        document_has_topics = exists().where(document_topics.c.document_id == DocumentModel.id)
        statement = (
            select(
                DocumentModel.id,
                DocumentModel.title,
                DocumentModel.type,
                DocumentModel.status,
                DocumentModel.summary,
                DocumentModel.created_at,
            )
            .join(document_tags, document_tags.c.document_id == DocumentModel.id)
            .join(TagModel, TagModel.id == document_tags.c.tag_id)
            .where(DocumentModel.user_id == user_id)
            .where(TagModel.user_id == user_id)
            .where(TagModel.name == name)
            .where(~document_has_topics)
            .order_by(DocumentModel.created_at.desc())
            .limit(limit)
        )
        return [topic_document_record(row) for row in (await self._session.execute(statement)).all()]

    async def _fallback_tag_documents_by_name(self, *, user_id: UUID, names: set[str]) -> dict[str, list[TopicDocumentRecord]]:
        if not names:
            return {}
        document_has_topics = exists().where(document_topics.c.document_id == DocumentModel.id)
        statement = (
            select(
                TagModel.name.label("topic_name"),
                DocumentModel.id,
                DocumentModel.title,
                DocumentModel.type,
                DocumentModel.status,
                DocumentModel.summary,
                DocumentModel.created_at,
            )
            .join(document_tags, document_tags.c.document_id == DocumentModel.id)
            .join(TagModel, TagModel.id == document_tags.c.tag_id)
            .where(DocumentModel.user_id == user_id)
            .where(TagModel.user_id == user_id)
            .where(TagModel.name.in_(names))
            .where(~document_has_topics)
            .order_by(TagModel.name.asc(), DocumentModel.created_at.desc())
        )
        grouped: dict[str, list[TopicDocumentRecord]] = {}
        for row in (await self._session.execute(statement)).all():
            grouped.setdefault(row.topic_name, []).append(topic_document_record(row))
        return grouped


def max_date(left: datetime | None, right: datetime | None) -> datetime | None:
    if left is None:
        return right
    if right is None:
        return left
    return max(left, right)


def topic_document_record(row: Any) -> TopicDocumentRecord:
    return TopicDocumentRecord(
        id=row.id,
        title=row.title,
        type=row.type.value,
        status=row.status.value,
        summary=row.summary,
        created_at=row.created_at,
    )
