from uuid import UUID

from dishka.integrations.fastapi import FromDishka, inject
from fastapi import APIRouter, Query

from src.application.use_cases.knowledge_graph import (
    CreateKnowledgeGraphConcernUseCase,
    GetKnowledgeGraphInsightsUseCase,
    GetKnowledgeGraphUseCase,
    RecomputeKnowledgeGraphUseCase,
)
from src.domain.value_objects.document_type import DocumentType
from src.presentation.dependencies.auth import CurrentUser
from src.presentation.mappers.knowledge_graph_mapper import (
    to_knowledge_graph_concern_response,
    to_knowledge_graph_insights_response,
    to_knowledge_graph_response,
)
from src.presentation.schemas.knowledge_graph import (
    KnowledgeGraphConcernCreateRequest,
    KnowledgeGraphConcernResponse,
    KnowledgeGraphInsightsResponse,
    KnowledgeGraphResponse,
)

router = APIRouter(prefix="/knowledge-graph", tags=["knowledge-graph"])


@router.get("", response_model=KnowledgeGraphResponse)
@inject
async def get_knowledge_graph(
    current_user: CurrentUser,
    use_case: FromDishka[GetKnowledgeGraphUseCase],
    document_limit: int = Query(default=80, ge=1, le=200),
    topic_limit: int = Query(default=20, ge=1, le=50),
    collection_id: UUID | None = Query(default=None),
    tag: str | None = Query(default=None, min_length=1, max_length=100),
    topic: str | None = Query(default=None, min_length=1, max_length=100),
    document_type: DocumentType | None = Query(default=None),
    recency_days: int | None = Query(default=None, ge=1, le=3650),
) -> KnowledgeGraphResponse:
    result = await use_case(
        user_id=current_user.id,
        document_limit=document_limit,
        topic_limit=topic_limit,
        collection_id=collection_id,
        tag_name=tag,
        topic_name=topic,
        document_type=document_type,
        recency_days=recency_days,
    )
    return to_knowledge_graph_response(result)


@router.get("/insights", response_model=KnowledgeGraphInsightsResponse)
@inject
async def get_knowledge_graph_insights(
    current_user: CurrentUser,
    use_case: FromDishka[GetKnowledgeGraphInsightsUseCase],
    document_limit: int = Query(default=120, ge=1, le=300),
    topic_limit: int = Query(default=40, ge=1, le=100),
    collection_id: UUID | None = Query(default=None),
    tag: str | None = Query(default=None, min_length=1, max_length=100),
    topic: str | None = Query(default=None, min_length=1, max_length=100),
    document_type: DocumentType | None = Query(default=None),
    recency_days: int | None = Query(default=None, ge=1, le=3650),
) -> KnowledgeGraphInsightsResponse:
    result = await use_case(
        user_id=current_user.id,
        document_limit=document_limit,
        topic_limit=topic_limit,
        collection_id=collection_id,
        tag_name=tag,
        topic_name=topic,
        document_type=document_type,
        recency_days=recency_days,
    )
    return to_knowledge_graph_insights_response(result)


@router.post("/recompute", response_model=KnowledgeGraphResponse)
@inject
async def recompute_knowledge_graph(
    current_user: CurrentUser,
    use_case: FromDishka[RecomputeKnowledgeGraphUseCase],
    document_limit: int = Query(default=80, ge=1, le=200),
    topic_limit: int = Query(default=20, ge=1, le=50),
    collection_id: UUID | None = Query(default=None),
    tag: str | None = Query(default=None, min_length=1, max_length=100),
    topic: str | None = Query(default=None, min_length=1, max_length=100),
    document_type: DocumentType | None = Query(default=None),
    recency_days: int | None = Query(default=None, ge=1, le=3650),
) -> KnowledgeGraphResponse:
    result = await use_case(
        user_id=current_user.id,
        document_limit=document_limit,
        topic_limit=topic_limit,
        collection_id=collection_id,
        tag_name=tag,
        topic_name=topic,
        document_type=document_type,
        recency_days=recency_days,
    )
    return to_knowledge_graph_response(result)


@router.post("/concerns", response_model=KnowledgeGraphConcernResponse, status_code=201)
@inject
async def create_knowledge_graph_concern(
    payload: KnowledgeGraphConcernCreateRequest,
    current_user: CurrentUser,
    use_case: FromDishka[CreateKnowledgeGraphConcernUseCase],
) -> KnowledgeGraphConcernResponse:
    result = await use_case(
        user_id=current_user.id,
        message=payload.message,
        node_id=payload.node_id,
        node_kind=payload.node_kind,
        node_label=payload.node_label,
    )
    return to_knowledge_graph_concern_response(result)
