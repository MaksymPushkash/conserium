from uuid import UUID

from fastapi import Depends, Query, Response, status

from src.auth.auth import CurrentUser
from src.compare.dependencies import get_compare_llm_service, get_compare_query_executor, get_compare_service
from src.compare.schemas import CompareDocumentsRequest, CompareDocumentsResponse, CompareListResponse
from src.compare.service import CompareService
from src.kit.ai.llm_service import LLMService
from src.postgres import AsyncReadSession, AsyncSession, get_db_read_session, get_db_session
from src.query.service import QueryExecutor
from src.routing import APIRouter

router = APIRouter(prefix="/compare", tags=["compare"])


@router.post("/documents", response_model=CompareDocumentsResponse)
async def compare_documents(
    current_user: CurrentUser,
    body: CompareDocumentsRequest,
    session: AsyncSession = Depends(get_db_session),
    service: CompareService = Depends(get_compare_service),
    query_executor: QueryExecutor = Depends(get_compare_query_executor),
    llm_service: LLMService = Depends(get_compare_llm_service),
) -> CompareDocumentsResponse:
    return await service.compare_documents(
        session,
        query_executor=query_executor,
        llm_service=llm_service,
        user_id=current_user.id,
        body=body,
    )


@router.get("/results", response_model=CompareListResponse)
async def list_compare_results(
    current_user: CurrentUser,
    session: AsyncReadSession = Depends(get_db_read_session),
    service: CompareService = Depends(get_compare_service),
    collection_id: UUID | None = None,
    limit: int = Query(default=20, ge=1, le=50),
    offset: int = Query(default=0, ge=0),
) -> CompareListResponse:
    return await service.list_results(
        session,
        user_id=current_user.id,
        collection_id=collection_id,
        limit=limit,
        offset=offset,
    )


@router.get("/results/{comparison_id}", response_model=CompareDocumentsResponse)
async def get_compare_result(
    current_user: CurrentUser,
    comparison_id: UUID,
    session: AsyncReadSession = Depends(get_db_read_session),
    service: CompareService = Depends(get_compare_service),
) -> CompareDocumentsResponse:
    return await service.get_result(session, user_id=current_user.id, comparison_id=comparison_id)


@router.delete("/results/{comparison_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_compare_result(
    current_user: CurrentUser,
    comparison_id: UUID,
    session: AsyncSession = Depends(get_db_session),
    service: CompareService = Depends(get_compare_service),
) -> Response:
    await service.delete_result(session, user_id=current_user.id, comparison_id=comparison_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


__all__ = ["router"]
