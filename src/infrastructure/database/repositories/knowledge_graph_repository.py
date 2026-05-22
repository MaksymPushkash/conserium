from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import delete, exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.application.ports.persistence.knowledge_graph_repository import (
    IKnowledgeGraphRepository,
    KnowledgeEdgeRecord,
    KnowledgeGraphConcernRecord,
    KnowledgeGraphRecord,
)
from src.domain.value_objects.document_type import DocumentType
from src.infrastructure.database.models.base import document_tags, document_topics
from src.infrastructure.database.models.document import DocumentModel
from src.infrastructure.database.models.knowledge_edge import KnowledgeEdgeModel
from src.infrastructure.database.models.knowledge_graph_concern import KnowledgeGraphConcernModel
from src.infrastructure.database.models.tag import TagModel
from src.infrastructure.database.models.topic import TopicModel


class SQLAlchemyKnowledgeGraphRepository(IKnowledgeGraphRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_topic_document_links(
        self,
        user_id: UUID,
        *,
        document_limit: int,
        topic_limit: int,
        collection_id: UUID | None = None,
        tag_name: str | None = None,
        topic_name: str | None = None,
        document_type: DocumentType | None = None,
        recency_days: int | None = None,
    ) -> list[KnowledgeGraphRecord]:
        links = [
            *await self._stored_topic_links(
                user_id,
                document_limit=document_limit,
                collection_id=collection_id,
                tag_name=tag_name,
                topic_name=topic_name,
                document_type=document_type,
                recency_days=recency_days,
            ),
            *await self._fallback_tag_links(
                user_id,
                document_limit=document_limit,
                collection_id=collection_id,
                tag_name=tag_name,
                topic_name=topic_name,
                document_type=document_type,
                recency_days=recency_days,
            ),
        ]
        topic_counts: dict[str, int] = {}
        for link in links:
            topic_counts[link.topic_name] = topic_counts.get(link.topic_name, 0) + 1
        allowed_topics = {
            topic
            for topic, _count in sorted(topic_counts.items(), key=lambda item: (-item[1], item[0]))[:topic_limit]
        }
        filtered = [link for link in links if link.topic_name in allowed_topics]
        return filtered[: document_limit * 3]

    async def list_edges(self, user_id: UUID) -> list[KnowledgeEdgeRecord]:
        result = await self._session.execute(
            select(KnowledgeEdgeModel)
            .where(KnowledgeEdgeModel.user_id == user_id)
            .order_by(KnowledgeEdgeModel.score.desc())
        )
        return [
            KnowledgeEdgeRecord(
                source_document_id=model.source_document_id,
                target_document_id=model.target_document_id,
                relation_type=model.relation_type,
                score=model.score,
                evidence=list(model.evidence),
            )
            for model in result.scalars().all()
        ]

    async def replace_edges(self, user_id: UUID, edges: list[KnowledgeEdgeRecord]) -> None:
        await self._session.execute(delete(KnowledgeEdgeModel).where(KnowledgeEdgeModel.user_id == user_id))
        self._session.add_all(
            KnowledgeEdgeModel(
                user_id=user_id,
                source_document_id=edge.source_document_id,
                target_document_id=edge.target_document_id,
                relation_type=edge.relation_type,
                score=edge.score,
                evidence=edge.evidence,
            )
            for edge in edges
        )

    async def create_concern(
        self,
        *,
        concern_id: UUID,
        user_id: UUID,
        node_id: str | None,
        node_kind: str | None,
        node_label: str | None,
        message: str,
    ) -> KnowledgeGraphConcernRecord:
        model = KnowledgeGraphConcernModel(
            id=concern_id,
            user_id=user_id,
            node_id=node_id,
            node_kind=node_kind,
            node_label=node_label,
            message=message,
            status="open",
        )
        self._session.add(model)
        await self._session.flush()
        await self._session.refresh(model)
        return KnowledgeGraphConcernRecord(
            id=model.id,
            user_id=model.user_id,
            node_id=model.node_id,
            node_kind=model.node_kind,
            node_label=model.node_label,
            message=model.message,
            status=model.status,
            created_at=model.created_at,
        )

    async def _stored_topic_links(
        self,
        user_id: UUID,
        *,
        document_limit: int,
        collection_id: UUID | None,
        tag_name: str | None,
        topic_name: str | None,
        document_type: DocumentType | None,
        recency_days: int | None,
    ) -> list[KnowledgeGraphRecord]:
        statement = (
            select(
                DocumentModel.id,
                DocumentModel.title,
                DocumentModel.type,
                DocumentModel.collection_id,
                DocumentModel.summary,
                DocumentModel.created_at,
                DocumentModel.updated_at,
                DocumentModel.suggested_questions,
                TopicModel.name.label("topic_name"),
            )
            .join(document_topics, document_topics.c.document_id == DocumentModel.id)
            .join(TopicModel, TopicModel.id == document_topics.c.topic_id)
            .where(DocumentModel.user_id == user_id)
            .where(TopicModel.user_id == user_id)
            .order_by(DocumentModel.created_at.desc())
            .limit(document_limit * 3)
        )
        if topic_name:
            statement = statement.where(func.lower(TopicModel.name) == topic_name.casefold())
        statement = apply_document_filters(
            statement,
            user_id=user_id,
            collection_id=collection_id,
            tag_name=tag_name,
            document_type=document_type,
            recency_days=recency_days,
        )
        rows = (await self._session.execute(statement)).all()
        return [
            KnowledgeGraphRecord(
                document_id=row.id,
                document_title=row.title,
                document_type=row.type.value,
                topic_name=row.topic_name,
                collection_id=row.collection_id,
                summary=row.summary,
                created_at=row.created_at,
                updated_at=row.updated_at,
                suggested_questions=list(row.suggested_questions or []),
            )
            for row in rows
        ]

    async def _fallback_tag_links(
        self,
        user_id: UUID,
        *,
        document_limit: int,
        collection_id: UUID | None,
        tag_name: str | None,
        topic_name: str | None,
        document_type: DocumentType | None,
        recency_days: int | None,
    ) -> list[KnowledgeGraphRecord]:
        document_has_topics = exists().where(document_topics.c.document_id == DocumentModel.id)
        statement = (
            select(
                DocumentModel.id,
                DocumentModel.title,
                DocumentModel.type,
                DocumentModel.collection_id,
                DocumentModel.summary,
                DocumentModel.created_at,
                DocumentModel.updated_at,
                DocumentModel.suggested_questions,
                TagModel.name.label("topic_name"),
            )
            .join(document_tags, document_tags.c.document_id == DocumentModel.id)
            .join(TagModel, TagModel.id == document_tags.c.tag_id)
            .where(DocumentModel.user_id == user_id)
            .where(TagModel.user_id == user_id)
            .where(~document_has_topics)
            .order_by(DocumentModel.created_at.desc())
            .limit(document_limit * 3)
        )
        if topic_name:
            statement = statement.where(func.lower(TagModel.name) == topic_name.casefold())
        statement = apply_document_filters(
            statement,
            user_id=user_id,
            collection_id=collection_id,
            tag_name=tag_name,
            document_type=document_type,
            recency_days=recency_days,
        )
        rows = (await self._session.execute(statement)).all()
        return [
            KnowledgeGraphRecord(
                document_id=row.id,
                document_title=row.title,
                document_type=row.type.value,
                topic_name=row.topic_name,
                collection_id=row.collection_id,
                summary=row.summary,
                created_at=row.created_at,
                updated_at=row.updated_at,
                suggested_questions=list(row.suggested_questions or []),
            )
            for row in rows
        ]


def apply_document_filters(
    statement: Any,
    *,
    user_id: UUID,
    collection_id: UUID | None,
    tag_name: str | None,
    document_type: DocumentType | None,
    recency_days: int | None,
) -> Any:
    if collection_id:
        statement = statement.where(DocumentModel.collection_id == collection_id)
    if tag_name:
        statement = statement.where(document_tag_exists(user_id, tag_name))
    if document_type:
        statement = statement.where(DocumentModel.type == document_type)
    if recency_days:
        cutoff = datetime.now(UTC) - timedelta(days=recency_days)
        statement = statement.where(DocumentModel.created_at >= cutoff)
    return statement


def document_tag_exists(user_id: UUID, tag_name: str) -> Any:
    return (
        select(1)
        .select_from(document_tags.join(TagModel, TagModel.id == document_tags.c.tag_id))
        .where(document_tags.c.document_id == DocumentModel.id)
        .where(TagModel.user_id == user_id)
        .where(func.lower(TagModel.name) == tag_name.casefold())
        .exists()
    )
