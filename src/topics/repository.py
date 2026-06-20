import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import distinct, exists, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.base import document_tags, document_topics
from src.models.document import DocumentModel
from src.models.tag import TagModel
from src.models.topic import TopicModel
from src.models.topic_override import TopicOverrideModel
from src.models.topic_override_event import TopicOverrideEventModel


@dataclass(frozen=True, slots=True)
class TopicRecord:
    name: str
    document_count: int
    last_document_at: datetime | None
    source_names: tuple[str, ...] = ()
    pinned: bool = False
    ignored: bool = False


@dataclass(frozen=True, slots=True)
class TopicOverrideRecord:
    source_name: str
    display_name: str
    pinned: bool
    ignored: bool


@dataclass(frozen=True, slots=True)
class TopicOverrideEventRecord:
    action: str
    topic_name: str
    display_name: str | None
    source_names: tuple[str, ...]
    created_at: datetime


@dataclass(frozen=True, slots=True)
class TopicDocumentRecord:
    id: UUID
    title: str
    type: str
    status: str
    summary: str | None
    created_at: datetime


@dataclass(frozen=True, slots=True)
class TopicDetailRecord:
    topic: TopicRecord
    documents: list[TopicDocumentRecord]


class TopicRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @classmethod
    def from_session(cls, session: AsyncSession) -> "TopicRepository":
        return cls(session)

    async def list_by_user_id(self, user_id: UUID, *, limit: int, offset: int) -> list[TopicRecord]:
        topics = await self._merged_topics(user_id)
        topics = [topic for topic in topics if not topic.ignored]
        topics.sort(key=lambda topic: (not topic.pinned, -topic.document_count, topic.name))
        return topics[offset : offset + limit]

    async def count_by_user_id(self, user_id: UUID) -> int:
        return len([topic for topic in await self._merged_topics(user_id) if not topic.ignored])

    async def get_detail_by_name(
        self,
        user_id: UUID,
        *,
        name: str,
        document_limit: int,
    ) -> TopicDetailRecord | None:
        topics = await self._merged_topics(user_id)
        topic = next((record for record in topics if topic_matches(record, name) and not record.ignored), None)
        if topic is None:
            return None
        documents = await self._documents_for_topic_names(
            user_id=user_id,
            names=set(topic.source_names or (topic.name,)),
            limit=document_limit,
        )
        flat_documents = {
            document.id: document
            for topic_documents in documents.values()
            for document in topic_documents
        }
        ranked_documents = sorted(flat_documents.values(), key=lambda document: document.created_at, reverse=True)
        return TopicDetailRecord(topic=topic, documents=ranked_documents[:document_limit])

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
            if record.name.casefold() in requested_names and not record.ignored
        }
        source_names = {source for topic in topics.values() for source in (topic.source_names or (topic.name,))}
        source_documents = await self._documents_for_topic_names(
            user_id=user_id,
            names=source_names,
            limit=document_limit,
        )
        documents: dict[str, list[TopicDocumentRecord]] = {}
        for topic_name, topic in topics.items():
            deduped: dict[UUID, TopicDocumentRecord] = {}
            for source_name in topic.source_names or (topic.name,):
                for document in source_documents.get(source_name.casefold(), []):
                    deduped[document.id] = document
            documents[topic_name] = sorted(deduped.values(), key=lambda document: document.created_at, reverse=True)[:document_limit]
        return {
            topic_name: TopicDetailRecord(topic=topic, documents=documents.get(topic.name.casefold(), []))
            for topic_name, topic in topics.items()
        }

    async def list_overrides(self, user_id: UUID) -> list[TopicOverrideRecord]:
        result = await self._session.execute(
            select(TopicOverrideModel).where(TopicOverrideModel.user_id == user_id)
        )
        return [self._to_override_record(model) for model in result.scalars().all()]

    async def rename_topic(self, *, user_id: UUID, source_name: str, display_name: str) -> TopicRecord:
        await self._upsert_override(user_id=user_id, source_name=source_name, display_name=display_name)
        self._add_override_event(
            user_id=user_id,
            action="renamed",
            topic_name=source_name,
            display_name=display_name,
            source_names=[source_name],
        )
        return await self._get_managed_topic(user_id=user_id, display_name=display_name)

    async def merge_topics(self, *, user_id: UUID, source_names: list[str], display_name: str) -> TopicRecord:
        for source_name in source_names:
            await self._upsert_override(user_id=user_id, source_name=source_name, display_name=display_name)
        self._add_override_event(
            user_id=user_id,
            action="merged",
            topic_name=display_name,
            display_name=display_name,
            source_names=source_names,
        )
        return await self._get_managed_topic(user_id=user_id, display_name=display_name)

    async def set_pinned(self, *, user_id: UUID, name: str, pinned: bool) -> TopicRecord:
        topic = await self._find_topic(user_id=user_id, name=name)
        for source_name in topic.source_names or (topic.name,):
            await self._upsert_override(
                user_id=user_id,
                source_name=source_name,
                display_name=topic.name,
                pinned=pinned,
                ignored=False if pinned else None,
            )
        self._add_override_event(
            user_id=user_id,
            action="pinned" if pinned else "unpinned",
            topic_name=topic.name,
            display_name=topic.name,
            source_names=list(topic.source_names or (topic.name,)),
        )
        return await self._get_managed_topic(user_id=user_id, display_name=topic.name)

    async def set_ignored(self, *, user_id: UUID, name: str, ignored: bool) -> TopicRecord:
        topic = await self._find_topic(user_id=user_id, name=name)
        for source_name in topic.source_names or (topic.name,):
            await self._upsert_override(
                user_id=user_id,
                source_name=source_name,
                display_name=topic.name,
                ignored=ignored,
                pinned=False if ignored else None,
            )
        self._add_override_event(
            user_id=user_id,
            action="ignored" if ignored else "unignored",
            topic_name=topic.name,
            display_name=topic.name,
            source_names=list(topic.source_names or (topic.name,)),
        )
        return await self._get_managed_topic(user_id=user_id, display_name=topic.name)

    async def list_override_events(self, *, user_id: UUID, topic_name: str, limit: int) -> list[TopicOverrideEventRecord]:
        topic = await self._find_topic(user_id=user_id, name=topic_name)
        names = {topic.name.casefold(), *(source.casefold() for source in topic.source_names)}
        result = await self._session.execute(
            select(TopicOverrideEventModel)
            .where(TopicOverrideEventModel.user_id == user_id)
            .where(func.lower(TopicOverrideEventModel.topic_name).in_(names))
            .order_by(TopicOverrideEventModel.created_at.desc())
            .limit(limit)
        )
        return [
            TopicOverrideEventRecord(
                action=model.action,
                topic_name=model.topic_name,
                display_name=model.display_name,
                source_names=tuple(model.source_names or []),
                created_at=model.created_at,
            )
            for model in result.scalars().all()
        ]

    async def _merged_topics(self, user_id: UUID) -> list[TopicRecord]:
        raw_topics: dict[str, TopicRecord] = {}
        for record in await self._stored_topics(user_id):
            raw_topics[record.name] = record
        for record in await self._fallback_tag_topics(user_id):
            current = raw_topics.get(record.name)
            if current is None:
                raw_topics[record.name] = record
            else:
                raw_topics[record.name] = TopicRecord(
                    name=current.name,
                    document_count=current.document_count + record.document_count,
                    last_document_at=max_date(current.last_document_at, record.last_document_at),
                    source_names=(current.name,),
                )
        return merge_topic_overrides(list(raw_topics.values()), await self.list_overrides(user_id))

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
                source_names=(row.name,),
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
                source_names=(row.name,),
            )
            for row in rows
        ]

    async def _upsert_override(
        self,
        *,
        user_id: UUID,
        source_name: str,
        display_name: str,
        pinned: bool | None = None,
        ignored: bool | None = None,
    ) -> None:
        values = {
            "id": uuid.uuid4(),
            "user_id": user_id,
            "source_name": normalize_topic_name(source_name),
            "display_name": clean_topic_name(display_name),
        }
        update_values: dict[str, object] = {"display_name": values["display_name"]}
        if pinned is not None:
            values["pinned"] = pinned
            update_values["pinned"] = pinned
        if ignored is not None:
            values["ignored"] = ignored
            update_values["ignored"] = ignored
        await self._session.execute(
            pg_insert(TopicOverrideModel)
            .values(**values)
            .on_conflict_do_update(
                index_elements=[TopicOverrideModel.user_id, TopicOverrideModel.source_name],
                set_=update_values,
            )
        )

    def _add_override_event(
        self,
        *,
        user_id: UUID,
        action: str,
        topic_name: str,
        display_name: str | None,
        source_names: list[str],
    ) -> None:
        self._session.add(
            TopicOverrideEventModel(
                user_id=user_id,
                action=action,
                topic_name=clean_topic_name(topic_name),
                display_name=clean_topic_name(display_name) if display_name is not None else None,
                source_names=[clean_topic_name(source_name) for source_name in source_names],
                metadata_={},
            )
        )

    async def _find_topic(self, *, user_id: UUID, name: str) -> TopicRecord:
        normalized = normalize_topic_name(name)
        topic = next((topic for topic in await self._merged_topics(user_id) if topic_matches(topic, normalized)), None)
        if topic is None:
            topic = TopicRecord(name=normalized, document_count=0, last_document_at=None, source_names=(normalized,))
        return topic

    async def _get_managed_topic(self, *, user_id: UUID, display_name: str) -> TopicRecord:
        topic = next(
            (topic for topic in await self._merged_topics(user_id) if topic.name.casefold() == normalize_topic_name(display_name).casefold()),
            None,
        )
        if topic is None:
            display = clean_topic_name(display_name)
            return TopicRecord(name=display, document_count=0, last_document_at=None, source_names=(normalize_topic_name(display),))
        return topic

    @staticmethod
    def _to_override_record(model: TopicOverrideModel) -> TopicOverrideRecord:
        return TopicOverrideRecord(
            source_name=model.source_name,
            display_name=model.display_name,
            pinned=model.pinned,
            ignored=model.ignored,
        )

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


def clean_topic_name(value: str) -> str:
    return " ".join(value.strip().split())[:100]


def normalize_topic_name(value: str) -> str:
    return clean_topic_name(value).casefold()


def merge_topic_overrides(raw_topics: list[TopicRecord], overrides: list[TopicOverrideRecord]) -> list[TopicRecord]:
    overrides_by_source = {override.source_name.casefold(): override for override in overrides}
    merged: dict[str, TopicRecord] = {}
    for topic in raw_topics:
        override = overrides_by_source.get(topic.name.casefold())
        display_name = override.display_name if override else topic.name
        source_names = tuple(topic.source_names or (topic.name,))
        pinned = bool(override.pinned) if override else False
        ignored = bool(override.ignored) if override else False
        merge_key = display_name.casefold()
        current = merged.get(merge_key)
        if current is None:
            merged[merge_key] = TopicRecord(
                name=display_name,
                document_count=topic.document_count,
                last_document_at=topic.last_document_at,
                source_names=source_names,
                pinned=pinned,
                ignored=ignored,
            )
            continue
        merged[merge_key] = TopicRecord(
            name=current.name,
            document_count=current.document_count + topic.document_count,
            last_document_at=max_date(current.last_document_at, topic.last_document_at),
            source_names=tuple(dict.fromkeys([*current.source_names, *source_names])),
            pinned=current.pinned or pinned,
            ignored=current.ignored and ignored,
        )
    return list(merged.values())


def topic_matches(topic: TopicRecord, name: str) -> bool:
    normalized = name.casefold()
    return topic.name.casefold() == normalized or normalized in {source.casefold() for source in topic.source_names}


def topic_document_record(row: Any) -> TopicDocumentRecord:
    return TopicDocumentRecord(
        id=row.id,
        title=row.title,
        type=row.type.value,
        status=row.status.value,
        summary=row.summary,
        created_at=row.created_at,
    )


__all__ = [
    "TopicDetailRecord",
    "TopicDocumentRecord",
    "TopicOverrideEventRecord",
    "TopicOverrideRecord",
    "TopicRecord",
    "TopicRepository",
    "clean_topic_name",
    "max_date",
    "merge_topic_overrides",
    "normalize_topic_name",
    "topic_document_record",
    "topic_matches",
]
