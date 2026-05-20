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
    ) -> list[KnowledgeGraphRecord]:
        links = [
            *await self._stored_topic_links(user_id, document_limit=document_limit, topic_limit=topic_limit),
            *await self._fallback_tag_links(user_id, document_limit=document_limit, topic_limit=topic_limit),
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
        topic_limit: int,
    ) -> list[KnowledgeGraphRecord]:
        statement = (
            select(
                DocumentModel.id,
                DocumentModel.title,
                DocumentModel.type,
                TopicModel.name.label("topic_name"),
            )
            .join(document_topics, document_topics.c.document_id == DocumentModel.id)
            .join(TopicModel, TopicModel.id == document_topics.c.topic_id)
            .where(DocumentModel.user_id == user_id)
            .where(TopicModel.user_id == user_id)
            .where(TopicModel.name.in_(top_topic_names_subquery(user_id, topic_limit)))
            .order_by(DocumentModel.created_at.desc())
            .limit(document_limit * 3)
        )
        rows = (await self._session.execute(statement)).all()
        return [
            KnowledgeGraphRecord(
                document_id=row.id,
                document_title=row.title,
                document_type=row.type.value,
                topic_name=row.topic_name,
            )
            for row in rows
        ]

    async def _fallback_tag_links(
        self,
        user_id: UUID,
        *,
        document_limit: int,
        topic_limit: int,
    ) -> list[KnowledgeGraphRecord]:
        document_has_topics = exists().where(document_topics.c.document_id == DocumentModel.id)
        statement = (
            select(
                DocumentModel.id,
                DocumentModel.title,
                DocumentModel.type,
                TagModel.name.label("topic_name"),
            )
            .join(document_tags, document_tags.c.document_id == DocumentModel.id)
            .join(TagModel, TagModel.id == document_tags.c.tag_id)
            .where(DocumentModel.user_id == user_id)
            .where(TagModel.user_id == user_id)
            .where(~document_has_topics)
            .where(TagModel.name.in_(top_tag_names_subquery(user_id, topic_limit)))
            .order_by(DocumentModel.created_at.desc())
            .limit(document_limit * 3)
        )
        rows = (await self._session.execute(statement)).all()
        return [
            KnowledgeGraphRecord(
                document_id=row.id,
                document_title=row.title,
                document_type=row.type.value,
                topic_name=row.topic_name,
            )
            for row in rows
        ]


def top_topic_names_subquery(user_id: UUID, topic_limit: int) -> Any:
    return (
        select(TopicModel.name)
        .join(document_topics, document_topics.c.topic_id == TopicModel.id)
        .join(DocumentModel, DocumentModel.id == document_topics.c.document_id)
        .where(TopicModel.user_id == user_id)
        .where(DocumentModel.user_id == user_id)
        .group_by(TopicModel.name)
        .order_by(func.count(DocumentModel.id).desc(), TopicModel.name.asc())
        .limit(topic_limit)
    )


def top_tag_names_subquery(user_id: UUID, topic_limit: int) -> Any:
    document_has_topics = exists().where(document_topics.c.document_id == DocumentModel.id)
    return (
        select(TagModel.name)
        .join(document_tags, document_tags.c.tag_id == TagModel.id)
        .join(DocumentModel, DocumentModel.id == document_tags.c.document_id)
        .where(TagModel.user_id == user_id)
        .where(DocumentModel.user_id == user_id)
        .where(~document_has_topics)
        .group_by(TagModel.name)
        .order_by(func.count(DocumentModel.id).desc(), TagModel.name.asc())
        .limit(topic_limit)
    )
