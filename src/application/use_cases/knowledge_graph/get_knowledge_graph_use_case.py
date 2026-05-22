from uuid import UUID, uuid4

from src.application.dtos.knowledge_graph_dtos import (
    KnowledgeGraphConcernDTO,
    KnowledgeGraphDTO,
    KnowledgeGraphEdgeDTO,
    KnowledgeGraphNodeDTO,
)
from src.application.ports.persistence.knowledge_graph_repository import KnowledgeEdgeRecord, KnowledgeGraphRecord
from src.application.ports.persistence.unit_of_work import IUnitOfWork
from src.domain.exceptions import ValidationException
from src.domain.value_objects.document_type import DocumentType


class GetKnowledgeGraphUseCase:
    def __init__(self, uow: IUnitOfWork) -> None:
        self._uow = uow

    async def __call__(
        self,
        *,
        user_id: UUID,
        document_limit: int = 80,
        topic_limit: int = 20,
        collection_id: UUID | None = None,
        tag_name: str | None = None,
        topic_name: str | None = None,
        document_type: DocumentType | None = None,
        recency_days: int | None = None,
    ) -> KnowledgeGraphDTO:
        async with self._uow:
            links = await self._uow.knowledge_graph_repo.list_topic_document_links(
                user_id,
                document_limit=document_limit,
                topic_limit=topic_limit,
                collection_id=collection_id,
                tag_name=normalize_optional_text(tag_name),
                topic_name=normalize_optional_text(topic_name),
                document_type=document_type,
                recency_days=recency_days,
            )
            document_edges = await self._uow.knowledge_graph_repo.list_edges(user_id)

        return knowledge_graph_from_records(links, document_edges_for_links(document_edges, links))


class RecomputeKnowledgeGraphUseCase:
    def __init__(self, uow: IUnitOfWork) -> None:
        self._uow = uow

    async def __call__(
        self,
        *,
        user_id: UUID,
        document_limit: int = 80,
        topic_limit: int = 20,
        collection_id: UUID | None = None,
        tag_name: str | None = None,
        topic_name: str | None = None,
        document_type: DocumentType | None = None,
        recency_days: int | None = None,
    ) -> KnowledgeGraphDTO:
        async with self._uow:
            links = await self._uow.knowledge_graph_repo.list_topic_document_links(
                user_id,
                document_limit=document_limit,
                topic_limit=topic_limit,
                collection_id=collection_id,
                tag_name=normalize_optional_text(tag_name),
                topic_name=normalize_optional_text(topic_name),
                document_type=document_type,
                recency_days=recency_days,
            )
            document_edges = document_relation_edges(links)
            await self._uow.knowledge_graph_repo.replace_edges(user_id, document_edges)
            await self._uow.commit()

        return knowledge_graph_from_records(links, document_edges)


class CreateKnowledgeGraphConcernUseCase:
    def __init__(self, uow: IUnitOfWork) -> None:
        self._uow = uow

    async def __call__(
        self,
        *,
        user_id: UUID,
        message: str,
        node_id: str | None = None,
        node_kind: str | None = None,
        node_label: str | None = None,
    ) -> KnowledgeGraphConcernDTO:
        normalized_message = message.strip()
        if not normalized_message:
            raise ValidationException("concern message cannot be empty")
        async with self._uow:
            record = await self._uow.knowledge_graph_repo.create_concern(
                concern_id=uuid4(),
                user_id=user_id,
                node_id=normalize_optional_text(node_id),
                node_kind=normalize_optional_text(node_kind),
                node_label=normalize_optional_text(node_label),
                message=normalized_message,
            )
            await self._uow.commit()
        return KnowledgeGraphConcernDTO(
            id=record.id,
            user_id=record.user_id,
            node_id=record.node_id,
            node_kind=record.node_kind,
            node_label=record.node_label,
            message=record.message,
            status=record.status,
            created_at=record.created_at,
        )


def knowledge_graph_from_records(
    links: list[KnowledgeGraphRecord],
    document_edges: list[KnowledgeEdgeRecord],
) -> KnowledgeGraphDTO:
    nodes: dict[str, KnowledgeGraphNodeDTO] = {}
    edges: dict[str, KnowledgeGraphEdgeDTO] = {}
    for link in links:
        topic_id = topic_node_id(link.topic_name)
        document_id = document_node_id(str(link.document_id))
        nodes[topic_id] = KnowledgeGraphNodeDTO(id=topic_id, kind="topic", label=link.topic_name)
        nodes[document_id] = KnowledgeGraphNodeDTO(
            id=document_id,
            kind="document",
            label=link.document_title,
            detail=link.document_type,
            collection_id=link.collection_id,
            summary=link.summary,
            created_at=link.created_at,
            updated_at=link.updated_at,
            suggested_questions=link.suggested_questions,
        )
        edge_id = f"{topic_id}:{document_id}"
        edges[edge_id] = KnowledgeGraphEdgeDTO(
            id=edge_id,
            source_id=topic_id,
            target_id=document_id,
            relation_type="same_topic",
            label="same topic",
            score=1.0,
        )
    for edge in document_edges:
        source_id = document_node_id(str(edge.source_document_id))
        target_id = document_node_id(str(edge.target_document_id))
        edge_id = f"{source_id}:{target_id}:{edge.relation_type}"
        edges[edge_id] = KnowledgeGraphEdgeDTO(
            id=edge_id,
            source_id=source_id,
            target_id=target_id,
            relation_type=edge.relation_type,
            label=edge.relation_type.replace("_", " "),
            score=edge.score,
        )

    return KnowledgeGraphDTO(nodes=list(nodes.values()), edges=list(edges.values()))


def document_edges_for_links(
    document_edges: list[KnowledgeEdgeRecord],
    links: list[KnowledgeGraphRecord],
) -> list[KnowledgeEdgeRecord]:
    document_ids = {link.document_id for link in links}
    return [
        edge
        for edge in document_edges
        if edge.source_document_id in document_ids and edge.target_document_id in document_ids
    ]


def topic_node_id(name: str) -> str:
    return f"topic:{name}"


def document_node_id(document_id: str) -> str:
    return f"document:{document_id}"


def document_relation_edges(links: list[KnowledgeGraphRecord]) -> list[KnowledgeEdgeRecord]:
    topic_documents: dict[str, list[KnowledgeGraphRecord]] = {}
    for link in links:
        topic_documents.setdefault(link.topic_name, []).append(link)

    evidence_by_pair: dict[tuple[UUID, UUID], list[str]] = {}
    for topic_name, topic_links in topic_documents.items():
        deduped_links = {link.document_id: link for link in topic_links}
        documents = sorted(deduped_links.values(), key=lambda link: str(link.document_id))
        for index, source in enumerate(documents):
            for target in documents[index + 1 :]:
                pair = (source.document_id, target.document_id)
                evidence_by_pair.setdefault(pair, []).append(topic_name)

    return [
        KnowledgeEdgeRecord(
            source_document_id=source_document_id,
            target_document_id=target_document_id,
            relation_type="same_topic",
            score=min(1.0, 0.65 + (len(evidence) * 0.1)),
            evidence=evidence[:5],
        )
        for (source_document_id, target_document_id), evidence in evidence_by_pair.items()
    ]


def normalize_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None
