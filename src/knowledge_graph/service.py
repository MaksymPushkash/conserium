from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from fastapi import Depends

from src.kit.exceptions import ValidationException
from src.knowledge_graph.repository import (
    KnowledgeEdgeRecord,
    KnowledgeGraphRecord,
    KnowledgeGraphRepository,
)
from src.knowledge_graph.schemas import (
    KnowledgeGraphConcernCreateRequest,
    KnowledgeGraphConcernDTO,
    KnowledgeGraphConcernResponse,
    KnowledgeGraphDTO,
    KnowledgeGraphEdgeDTO,
    KnowledgeGraphEdgeResponse,
    KnowledgeGraphInsightDTO,
    KnowledgeGraphInsightResponse,
    KnowledgeGraphInsightsDTO,
    KnowledgeGraphInsightsResponse,
    KnowledgeGraphNodeDTO,
    KnowledgeGraphNodeResponse,
    KnowledgeGraphResponse,
)
from src.postgres import AsyncSession, get_db_session
from src.topics.repository import TopicRepository

if TYPE_CHECKING:
    from src.documents.types import DocumentType
    from src.topics.repository import TopicOverrideRecord


class KnowledgeGraphFilters:
    def __init__(
        self,
        *,
        document_limit: int,
        topic_limit: int,
        collection_id: UUID | None,
        tag_name: str | None,
        topic_name: str | None,
        document_type: DocumentType | None,
        recency_days: int | None,
    ) -> None:
        self.document_limit = document_limit
        self.topic_limit = topic_limit
        self.collection_id = collection_id
        self.tag_name = tag_name
        self.topic_name = topic_name
        self.document_type = document_type
        self.recency_days = recency_days


class KnowledgeGraphService:
    def __init__(
        self,
        session: AsyncSession,
        knowledge_graph_repo: KnowledgeGraphRepository,
        topic_repo: TopicRepository,
    ) -> None:
        self._session = session
        self._knowledge_graph_repo = knowledge_graph_repo
        self._topic_repo = topic_repo

    async def get_graph(self, *, user_id: UUID, filters: KnowledgeGraphFilters) -> KnowledgeGraphResponse:
        links = await self._list_effective_links(
            user_id=user_id,
            document_limit=filters.document_limit,
            topic_limit=filters.topic_limit,
            collection_id=filters.collection_id,
            tag_name=filters.tag_name,
            topic_name=filters.topic_name,
            document_type=filters.document_type,
            recency_days=filters.recency_days,
        )
        document_edges = await self._knowledge_graph_repo.list_edges(user_id)
        result = knowledge_graph_from_records(links, document_edges_for_links(document_edges, links))
        return to_knowledge_graph_response(result)

    async def get_insights(self, *, user_id: UUID, filters: KnowledgeGraphFilters) -> KnowledgeGraphInsightsResponse:
        overrides = await self._topic_repo.list_overrides(user_id)
        links = await self._list_effective_links(
            user_id=user_id,
            document_limit=filters.document_limit,
            topic_limit=filters.topic_limit,
            collection_id=filters.collection_id,
            tag_name=filters.tag_name,
            topic_name=filters.topic_name,
            document_type=filters.document_type,
            recency_days=filters.recency_days,
            overrides=overrides,
        )
        document_edges = await self._knowledge_graph_repo.list_edges(user_id)
        graph = knowledge_graph_from_records(links, document_edges_for_links(document_edges, links))
        result = graph_insights(graph, overrides)
        return to_knowledge_graph_insights_response(result)

    async def recompute(self, *, user_id: UUID, filters: KnowledgeGraphFilters) -> KnowledgeGraphResponse:
        links = await self._list_effective_links(
            user_id=user_id,
            document_limit=filters.document_limit,
            topic_limit=filters.topic_limit,
            collection_id=filters.collection_id,
            tag_name=filters.tag_name,
            topic_name=filters.topic_name,
            document_type=filters.document_type,
            recency_days=filters.recency_days,
        )
        document_edges = document_relation_edges(links)
        await self._knowledge_graph_repo.replace_edges(user_id, document_edges)
        await self._session.flush()
        result = knowledge_graph_from_records(links, document_edges)
        return to_knowledge_graph_response(result)

    async def create_concern(
        self,
        *,
        user_id: UUID,
        payload: KnowledgeGraphConcernCreateRequest,
    ) -> KnowledgeGraphConcernResponse:
        normalized_message = payload.message.strip()
        if not normalized_message:
            raise ValidationException("concern message cannot be empty")
        record = await self._knowledge_graph_repo.create_concern(
            concern_id=uuid4(),
            user_id=user_id,
            node_id=normalize_optional_text(payload.node_id),
            node_kind=normalize_optional_text(payload.node_kind),
            node_label=normalize_optional_text(payload.node_label),
            message=normalized_message,
        )
        await self._session.flush()
        result = KnowledgeGraphConcernDTO(
            id=record.id,
            user_id=record.user_id,
            node_id=record.node_id,
            node_kind=record.node_kind,
            node_label=record.node_label,
            message=record.message,
            status=record.status,
            created_at=record.created_at,
        )
        return to_knowledge_graph_concern_response(result)

    async def _list_effective_links(
        self,
        *,
        user_id: UUID,
        document_limit: int,
        topic_limit: int,
        collection_id: UUID | None,
        tag_name: str | None,
        topic_name: str | None,
        document_type: DocumentType | None,
        recency_days: int | None,
        overrides: list[TopicOverrideRecord] | None = None,
    ) -> list[KnowledgeGraphRecord]:
        links = await self._knowledge_graph_repo.list_topic_document_links(
            user_id,
            document_limit=document_limit,
            topic_limit=effective_topic_limit(topic_limit, topic_name),
            collection_id=collection_id,
            tag_name=normalize_optional_text(tag_name),
            topic_name=None,
            document_type=document_type,
            recency_days=recency_days,
        )
        return apply_topic_overrides(
            links,
            overrides if overrides is not None else await self._topic_repo.list_overrides(user_id),
            topic_name=normalize_optional_text(topic_name),
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
        current_topic_node = nodes.get(topic_id)
        source_names = tuple(
            dict.fromkeys([*(current_topic_node.source_names if current_topic_node else ()), link.source_topic_name or link.topic_name])
        )
        nodes[topic_id] = KnowledgeGraphNodeDTO(
            id=topic_id,
            kind="topic",
            label=link.topic_name,
            source_names=source_names,
            is_pinned=(current_topic_node.is_pinned if current_topic_node else False) or link.topic_pinned,
            is_ignored=False,
        )
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


def graph_insights(graph: KnowledgeGraphDTO, overrides: list[TopicOverrideRecord]) -> KnowledgeGraphInsightsDTO:
    nodes_by_id = {node.id: node for node in graph.nodes}
    degree_by_id: dict[str, int] = {node.id: 0 for node in graph.nodes}
    for edge in graph.edges:
        degree_by_id[edge.source_id] = degree_by_id.get(edge.source_id, 0) + 1
        degree_by_id[edge.target_id] = degree_by_id.get(edge.target_id, 0) + 1

    topic_documents: dict[str, list[KnowledgeGraphNodeDTO]] = {
        node.id: [] for node in graph.nodes if node.kind == "topic"
    }
    for edge in graph.edges:
        source = nodes_by_id.get(edge.source_id)
        target = nodes_by_id.get(edge.target_id)
        if source is None or target is None:
            continue
        if source.kind == "topic" and target.kind == "document":
            topic_documents.setdefault(source.id, []).append(target)
        elif target.kind == "topic" and source.kind == "document":
            topic_documents.setdefault(target.id, []).append(source)

    isolated_topics = [node for node in graph.nodes if node.kind == "topic" and degree_by_id.get(node.id, 0) == 0]
    thin_topics = [
        nodes_by_id[topic_id]
        for topic_id, documents in topic_documents.items()
        if topic_id in nodes_by_id and 0 < len(documents) < 2
    ]
    stale_cutoff = datetime.now(UTC) - timedelta(days=180)
    stale_topics = [
        nodes_by_id[topic_id]
        for topic_id, documents in topic_documents.items()
        if topic_id in nodes_by_id and documents and all(node_is_stale(document, stale_cutoff) for document in documents)
    ]
    over_connected_documents = [
        node
        for node in graph.nodes
        if node.kind == "document" and degree_by_id.get(node.id, 0) >= 4
    ]
    pinned_topics = [node for node in graph.nodes if node.kind == "topic" and node.is_pinned]
    ignored_topics = ignored_topic_nodes(overrides)

    return KnowledgeGraphInsightsDTO(
        items=[
            insight(
                kind="isolated_topics",
                title="Isolated topics",
                description="Topics with no visible source documents in the current graph scope.",
                severity="medium",
                nodes=isolated_topics,
            ),
            insight(
                kind="thin_clusters",
                title="Thin clusters",
                description="Topics backed by only one visible document.",
                severity="low",
                nodes=thin_topics,
            ),
            insight(
                kind="stale_clusters",
                title="Stale clusters",
                description="Topics whose visible documents have not changed in more than 180 days.",
                severity="medium",
                nodes=stale_topics,
            ),
            insight(
                kind="over_connected_documents",
                title="Over-connected documents",
                description="Documents connected to many graph edges and likely acting as broad hubs.",
                severity="low",
                nodes=over_connected_documents,
            ),
            insight(
                kind="pinned_topics",
                title="Pinned topics",
                description="Topics manually marked as important.",
                severity="info",
                nodes=pinned_topics,
            ),
            insight(
                kind="ignored_topics",
                title="Ignored topics",
                description="Topics hidden by topic management rules.",
                severity="info",
                nodes=ignored_topics,
            ),
        ]
    )


def insight(
    *,
    kind: str,
    title: str,
    description: str,
    severity: str,
    nodes: list[KnowledgeGraphNodeDTO],
) -> KnowledgeGraphInsightDTO:
    return KnowledgeGraphInsightDTO(
        kind=kind,
        title=title,
        description=description,
        severity=severity,
        count=len(nodes),
        nodes=nodes[:8],
    )


def node_is_stale(node: KnowledgeGraphNodeDTO, stale_cutoff: datetime) -> bool:
    timestamp = node.updated_at or node.created_at
    return timestamp is not None and timestamp < stale_cutoff


def ignored_topic_nodes(overrides: list[TopicOverrideRecord]) -> list[KnowledgeGraphNodeDTO]:
    ignored: dict[str, list[str]] = {}
    for override in overrides:
        if override.ignored:
            ignored.setdefault(override.display_name, []).append(override.source_name)
    return [
        KnowledgeGraphNodeDTO(
            id=topic_node_id(display_name),
            kind="topic",
            label=display_name,
            source_names=tuple(source_names),
            is_ignored=True,
        )
        for display_name, source_names in sorted(ignored.items())
    ]


def apply_topic_overrides(
    links: list[KnowledgeGraphRecord],
    overrides: list[TopicOverrideRecord],
    *,
    topic_name: str | None,
) -> list[KnowledgeGraphRecord]:
    overrides_by_source = {override.source_name.casefold(): override for override in overrides}
    effective_links: list[KnowledgeGraphRecord] = []
    for link in links:
        override = overrides_by_source.get(link.topic_name.casefold())
        if override is not None and override.ignored:
            continue
        display_name = override.display_name if override is not None else link.topic_name
        if topic_name is not None and display_name.casefold() != topic_name.casefold():
            continue
        effective_links.append(
            KnowledgeGraphRecord(
                document_id=link.document_id,
                document_title=link.document_title,
                document_type=link.document_type,
                topic_name=display_name,
                collection_id=link.collection_id,
                summary=link.summary,
                created_at=link.created_at,
                updated_at=link.updated_at,
                suggested_questions=link.suggested_questions,
                source_topic_name=link.topic_name,
                topic_pinned=override.pinned if override is not None else False,
                topic_ignored=override.ignored if override is not None else False,
            )
        )
    return effective_links


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


def effective_topic_limit(topic_limit: int, topic_name: str | None) -> int:
    return max(topic_limit, 500) if normalize_optional_text(topic_name) is not None else topic_limit


def get_knowledge_graph_service(
    session: AsyncSession = Depends(get_db_session),
) -> KnowledgeGraphService:
    return KnowledgeGraphService(
        session,
        KnowledgeGraphRepository.from_session(session),
        TopicRepository.from_session(session),
    )


def to_knowledge_graph_response(dto: KnowledgeGraphDTO) -> KnowledgeGraphResponse:
    return KnowledgeGraphResponse(
        nodes=[to_knowledge_graph_node_response(node) for node in dto.nodes],
        edges=[
            KnowledgeGraphEdgeResponse(
                id=edge.id,
                source_id=edge.source_id,
                target_id=edge.target_id,
                relation_type=edge.relation_type,
                label=edge.label,
                score=edge.score,
            )
            for edge in dto.edges
        ],
    )


def to_knowledge_graph_insights_response(dto: KnowledgeGraphInsightsDTO) -> KnowledgeGraphInsightsResponse:
    return KnowledgeGraphInsightsResponse(
        items=[
            KnowledgeGraphInsightResponse(
                kind=item.kind,
                title=item.title,
                description=item.description,
                severity=item.severity,
                count=item.count,
                nodes=[to_knowledge_graph_node_response(node) for node in item.nodes],
            )
            for item in dto.items
        ]
    )


def to_knowledge_graph_node_response(node: KnowledgeGraphNodeDTO) -> KnowledgeGraphNodeResponse:
    return KnowledgeGraphNodeResponse(
        id=node.id,
        kind=node.kind,
        label=node.label,
        detail=node.detail,
        collection_id=node.collection_id,
        summary=node.summary,
        created_at=node.created_at,
        updated_at=node.updated_at,
        suggested_questions=node.suggested_questions,
        source_names=list(node.source_names),
        is_pinned=node.is_pinned,
        is_ignored=node.is_ignored,
    )


def to_knowledge_graph_concern_response(dto: KnowledgeGraphConcernDTO) -> KnowledgeGraphConcernResponse:
    return KnowledgeGraphConcernResponse(
        id=dto.id,
        node_id=dto.node_id,
        node_kind=dto.node_kind,
        node_label=dto.node_label,
        message=dto.message,
        status=dto.status,
        created_at=dto.created_at,
    )




__all__ = [
    "KnowledgeGraphFilters",
    "KnowledgeGraphService",
    "apply_topic_overrides",
    "document_edges_for_links",
    "document_node_id",
    "document_relation_edges",
    "effective_topic_limit",
    "get_knowledge_graph_service",
    "graph_insights",
    "knowledge_graph_from_records",
    "normalize_optional_text",
    "to_knowledge_graph_concern_response",
    "to_knowledge_graph_insights_response",
    "to_knowledge_graph_node_response",
    "to_knowledge_graph_response",
    "topic_node_id",
]
