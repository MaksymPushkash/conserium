from src.application.dtos.knowledge_graph_dtos import (
    KnowledgeGraphConcernDTO,
    KnowledgeGraphDTO,
    KnowledgeGraphInsightsDTO,
    KnowledgeGraphNodeDTO,
)
from src.presentation.schemas.knowledge_graph import (
    KnowledgeGraphConcernResponse,
    KnowledgeGraphEdgeResponse,
    KnowledgeGraphInsightResponse,
    KnowledgeGraphInsightsResponse,
    KnowledgeGraphNodeResponse,
    KnowledgeGraphResponse,
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
