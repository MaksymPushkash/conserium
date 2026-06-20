import hashlib

from fastapi import Depends, Query, Request, Response, status

from src.auth.auth import CurrentUser
from src.observability.rate_limit import limiter
from src.postgres import AsyncReadSession, AsyncSession, get_db_read_session, get_db_session, get_session_factory
from src.public_shares.schemas import AnswerShareListResponse, PublicAnswerShareResponse, PublicCollectionResponse
from src.public_shares.service import (
    PublicAskLedger,
    PublicShareService,
    get_public_query_graph_runner,
)
from src.query.agents.graph_runner import QueryGraphRunner
from src.query.schemas import PublicCollectionQueryResponse, QueryRequest
from src.routing import APIRouter

public_router = APIRouter(prefix="/public", tags=["public"])
answer_share_router = APIRouter(prefix="/answer-shares", tags=["answer-shares"])
router = APIRouter()


def get_public_share_service() -> PublicShareService:
    return PublicShareService(PublicAskLedger(get_session_factory()))


@public_router.get("/collections/{slug}", response_model=PublicCollectionResponse)
async def get_public_collection(
    slug: str,
    session: AsyncReadSession = Depends(get_db_read_session),
    service: PublicShareService = Depends(get_public_share_service),
) -> PublicCollectionResponse:
    return await service.get_public_collection(session, slug=slug)


@public_router.post("/collections/{slug}/query", response_model=PublicCollectionQueryResponse)
@limiter.limit("5/minute")
async def query_public_collection(
    request: Request,
    slug: str,
    body: QueryRequest,
    service: PublicShareService = Depends(get_public_share_service),
    graph_runner: QueryGraphRunner = Depends(get_public_query_graph_runner),
) -> PublicCollectionQueryResponse:
    return await service.query_public_collection(
        graph_runner=graph_runner,
        slug=slug,
        query=body.query,
        client_key=_public_client_key(request),
        limit=body.limit,
    )


@public_router.get("/answers/{slug}", response_model=PublicAnswerShareResponse)
@limiter.limit("60/minute")
async def get_public_answer_share(
    request: Request,
    slug: str,
    session: AsyncReadSession = Depends(get_db_read_session),
    service: PublicShareService = Depends(get_public_share_service),
) -> PublicAnswerShareResponse:
    return await service.get_public_answer_share(session, slug=slug)


@answer_share_router.get("", response_model=AnswerShareListResponse)
async def list_answer_shares(
    current_user: CurrentUser,
    session: AsyncReadSession = Depends(get_db_read_session),
    service: PublicShareService = Depends(get_public_share_service),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> AnswerShareListResponse:
    return await service.list_answer_shares(session, user_id=current_user.id, limit=limit, offset=offset)


@answer_share_router.delete("/{slug}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_answer_share(
    slug: str,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_db_session),
    service: PublicShareService = Depends(get_public_share_service),
) -> Response:
    await service.revoke_answer_share(session, user_id=current_user.id, slug=slug)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _public_client_key(request: Request) -> str:
    forwarded_for = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
    host = forwarded_for or (request.client.host if request.client else "unknown")
    user_agent = request.headers.get("user-agent", "unknown")[:200]
    return hashlib.sha256(f"{host}:{user_agent}".encode()).hexdigest()


router.include_router(answer_share_router)
router.include_router(public_router)


__all__ = [
    "answer_share_router",
    "get_public_share_service",
    "public_router",
    "router",
]
