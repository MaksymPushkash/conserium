from uuid import UUID

from fastapi import Depends, Query, status

from src.auth.auth import CurrentUser
from src.documents.types import DocumentType
from src.knowledge_graph.dependencies import get_knowledge_graph_service
from src.knowledge_graph.schemas import (
    KnowledgeGraphConcernCreateRequest,
    KnowledgeGraphConcernResponse,
    KnowledgeGraphInsightsResponse,
    KnowledgeGraphResponse,
)
from src.knowledge_graph.service import KnowledgeGraphFilters, KnowledgeGraphService
from src.routing import APIRouter

router = APIRouter(prefix="/knowledge-graph", tags=["knowledge-graph"])


@router.get("", response_model=KnowledgeGraphResponse)
async def get_knowledge_graph(
    current_user: CurrentUser,
    service: KnowledgeGraphService = Depends(get_knowledge_graph_service),
    document_limit: int = Query(default=80, ge=1, le=200),
    topic_limit: int = Query(default=20, ge=1, le=50),
    collection_id: UUID | None = Query(default=None),
    tag: str | None = Query(default=None, min_length=1, max_length=100),
    topic: str | None = Query(default=None, min_length=1, max_length=100),
    document_type: DocumentType | None = Query(default=None),
    recency_days: int | None = Query(default=None, ge=1, le=3650),
) -> KnowledgeGraphResponse:
    return await service.get_graph(
        user_id=current_user.id,
        filters=KnowledgeGraphFilters(
            document_limit=document_limit,
            topic_limit=topic_limit,
            collection_id=collection_id,
            tag_name=tag,
            topic_name=topic,
            document_type=document_type,
            recency_days=recency_days,
        ),
    )


@router.get("/insights", response_model=KnowledgeGraphInsightsResponse)
async def get_knowledge_graph_insights(
    current_user: CurrentUser,
    service: KnowledgeGraphService = Depends(get_knowledge_graph_service),
    document_limit: int = Query(default=120, ge=1, le=300),
    topic_limit: int = Query(default=40, ge=1, le=100),
    collection_id: UUID | None = Query(default=None),
    tag: str | None = Query(default=None, min_length=1, max_length=100),
    topic: str | None = Query(default=None, min_length=1, max_length=100),
    document_type: DocumentType | None = Query(default=None),
    recency_days: int | None = Query(default=None, ge=1, le=3650),
) -> KnowledgeGraphInsightsResponse:
    return await service.get_insights(
        user_id=current_user.id,
        filters=KnowledgeGraphFilters(
            document_limit=document_limit,
            topic_limit=topic_limit,
            collection_id=collection_id,
            tag_name=tag,
            topic_name=topic,
            document_type=document_type,
            recency_days=recency_days,
        ),
    )


@router.post("/recompute", response_model=KnowledgeGraphResponse)
async def recompute_knowledge_graph(
    current_user: CurrentUser,
    service: KnowledgeGraphService = Depends(get_knowledge_graph_service),
    document_limit: int = Query(default=80, ge=1, le=200),
    topic_limit: int = Query(default=20, ge=1, le=50),
    collection_id: UUID | None = Query(default=None),
    tag: str | None = Query(default=None, min_length=1, max_length=100),
    topic: str | None = Query(default=None, min_length=1, max_length=100),
    document_type: DocumentType | None = Query(default=None),
    recency_days: int | None = Query(default=None, ge=1, le=3650),
) -> KnowledgeGraphResponse:
    return await service.recompute(
        user_id=current_user.id,
        filters=KnowledgeGraphFilters(
            document_limit=document_limit,
            topic_limit=topic_limit,
            collection_id=collection_id,
            tag_name=tag,
            topic_name=topic,
            document_type=document_type,
            recency_days=recency_days,
        ),
    )


@router.post("/concerns", response_model=KnowledgeGraphConcernResponse, status_code=status.HTTP_201_CREATED)
async def create_knowledge_graph_concern(
    payload: KnowledgeGraphConcernCreateRequest,
    current_user: CurrentUser,
    service: KnowledgeGraphService = Depends(get_knowledge_graph_service),
) -> KnowledgeGraphConcernResponse:
    return await service.create_concern(user_id=current_user.id, payload=payload)


__all__ = ["router"]
