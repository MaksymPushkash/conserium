from src.application.dtos.knowledge_graph_dtos import KnowledgeGraphConcernDTO, KnowledgeGraphDTO
from src.presentation.schemas.knowledge_graph import (
    KnowledgeGraphConcernResponse,
    KnowledgeGraphEdgeResponse,
    KnowledgeGraphNodeResponse,
    KnowledgeGraphResponse,
)


def to_knowledge_graph_response(dto: KnowledgeGraphDTO) -> KnowledgeGraphResponse:
    return KnowledgeGraphResponse(
        nodes=[
            KnowledgeGraphNodeResponse(
                id=node.id,
                kind=node.kind,
                label=node.label,
                detail=node.detail,
                collection_id=node.collection_id,
                summary=node.summary,
                created_at=node.created_at,
                updated_at=node.updated_at,
                suggested_questions=node.suggested_questions,
            )
            for node in dto.nodes
        ],
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
