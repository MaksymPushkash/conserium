from __future__ import annotations

from typing import TYPE_CHECKING

from src.kit.exceptions import ResourceNotFoundException, ValidationException
from src.topics.repository import TopicDocumentRecord, TopicRecord, TopicRepository
from src.topics.schemas import (
    TopicDetailResponse,
    TopicDocumentResponse,
    TopicEventResponse,
    TopicListResponse,
    TopicResponse,
)

if TYPE_CHECKING:
    from uuid import UUID

    from src.postgres import AsyncReadSession, AsyncSession


class TopicService:
    async def list_topics(
        self,
        session: AsyncReadSession,
        *,
        user_id: UUID,
        limit: int,
        offset: int,
    ) -> TopicListResponse:
        repository = TopicRepository.from_session(session)
        records = await repository.list_by_user_id(user_id, limit=limit, offset=offset)
        total = await repository.count_by_user_id(user_id)
        return TopicListResponse(
            items=[_topic_response(record) for record in records],
            total=total,
            limit=limit,
            offset=offset,
        )

    async def get_detail(
        self,
        session: AsyncReadSession,
        *,
        user_id: UUID,
        name: str,
        document_limit: int,
    ) -> TopicDetailResponse:
        normalized_name = name.strip().lower()
        repository = TopicRepository.from_session(session)
        record = await repository.get_detail_by_name(
            user_id,
            name=normalized_name,
            document_limit=document_limit,
        )
        if record is None:
            raise ResourceNotFoundException("topic not found")
        events = await repository.list_override_events(user_id=user_id, topic_name=normalized_name, limit=10)
        return TopicDetailResponse(
            topic=_topic_response(record.topic),
            documents=[_topic_document_response(document) for document in record.documents],
            events=[
                TopicEventResponse(
                    action=event.action,
                    topic_name=event.topic_name,
                    display_name=event.display_name,
                    source_names=list(event.source_names),
                    created_at=event.created_at,
                )
                for event in events
            ],
        )

    async def rename(
        self,
        session: AsyncSession,
        *,
        user_id: UUID,
        name: str,
        display_name: str,
    ) -> TopicResponse:
        source_name = clean_topic_name(name)
        normalized_display_name = clean_topic_name(display_name)
        if not source_name or not normalized_display_name:
            raise ValidationException("topic name cannot be empty")
        record = await TopicRepository.from_session(session).rename_topic(
            user_id=user_id,
            source_name=source_name,
            display_name=normalized_display_name,
        )
        return _topic_response(record)

    async def merge(
        self,
        session: AsyncSession,
        *,
        user_id: UUID,
        name: str,
        source_names: list[str],
    ) -> TopicResponse:
        display_name = clean_topic_name(name)
        normalized_sources = unique_topic_names([*source_names, name])
        if not display_name or len(normalized_sources) < 2:
            raise ValidationException("at least two topics are required to merge")
        record = await TopicRepository.from_session(session).merge_topics(
            user_id=user_id,
            source_names=normalized_sources,
            display_name=display_name,
        )
        return _topic_response(record)

    async def pin(
        self,
        session: AsyncSession,
        *,
        user_id: UUID,
        name: str,
        pinned: bool,
    ) -> TopicResponse:
        topic_name = clean_topic_name(name)
        if not topic_name:
            raise ValidationException("topic name cannot be empty")
        record = await TopicRepository.from_session(session).set_pinned(user_id=user_id, name=topic_name, pinned=pinned)
        return _topic_response(record)

    async def ignore(
        self,
        session: AsyncSession,
        *,
        user_id: UUID,
        name: str,
        ignored: bool,
    ) -> TopicResponse:
        topic_name = clean_topic_name(name)
        if not topic_name:
            raise ValidationException("topic name cannot be empty")
        record = await TopicRepository.from_session(session).set_ignored(
            user_id=user_id,
            name=topic_name,
            ignored=ignored,
        )
        return _topic_response(record)


def _topic_response(record: TopicRecord) -> TopicResponse:
    return TopicResponse(
        name=record.name,
        document_count=record.document_count,
        last_document_at=record.last_document_at,
        source_names=list(record.source_names),
        pinned=record.pinned,
        ignored=record.ignored,
    )


def _topic_document_response(record: TopicDocumentRecord) -> TopicDocumentResponse:
    return TopicDocumentResponse(
        id=str(record.id),
        title=record.title,
        type=record.type,
        status=record.status,
        summary=record.summary,
        created_at=record.created_at,
    )


def clean_topic_name(value: str) -> str:
    return " ".join(value.strip().split())[:100]


def unique_topic_names(values: list[str]) -> list[str]:
    names: dict[str, str] = {}
    for value in values:
        name = clean_topic_name(value)
        if name:
            names.setdefault(name.casefold(), name)
    return list(names.values())


topics = TopicService()

__all__ = ["TopicService", "clean_topic_name", "topics", "unique_topic_names"]
