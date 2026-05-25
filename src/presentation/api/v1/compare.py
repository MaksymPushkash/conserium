from uuid import UUID

from dishka.integrations.fastapi import FromDishka, inject
from fastapi import APIRouter, Query, Response, status

from src.application.dtos.compare_dtos import DeleteCompareResultDTO, GetCompareResultDTO, ListCompareResultsDTO
from src.application.use_cases.compare import (
    CompareDocumentsUseCase,
    DeleteCompareResultUseCase,
    GetCompareResultUseCase,
    ListCompareResultsUseCase,
)
from src.presentation.dependencies.auth import CurrentUser
from src.presentation.mappers.compare_mapper import (
    to_compare_documents_dto,
    to_compare_documents_response,
    to_compare_list_response,
)
from src.presentation.schemas.compare import CompareDocumentsRequest, CompareDocumentsResponse, CompareListResponse

router = APIRouter(prefix="/compare", tags=["compare"])


@router.post("/documents", response_model=CompareDocumentsResponse)
@inject
async def compare_documents(
    current_user: CurrentUser,
    body: CompareDocumentsRequest,
    use_case: FromDishka[CompareDocumentsUseCase],
) -> CompareDocumentsResponse:
    result = await use_case(to_compare_documents_dto(body, current_user.id))
    return to_compare_documents_response(result)


@router.get("/results", response_model=CompareListResponse)
@inject
async def list_compare_results(
    current_user: CurrentUser,
    use_case: FromDishka[ListCompareResultsUseCase],
    collection_id: UUID | None = None,
    limit: int = Query(default=20, ge=1, le=50),
    offset: int = Query(default=0, ge=0),
) -> CompareListResponse:
    result = await use_case(
        ListCompareResultsDTO(
            user_id=current_user.id,
            collection_id=collection_id,
            limit=limit,
            offset=offset,
        )
    )
    return to_compare_list_response(result)


@router.get("/results/{comparison_id}", response_model=CompareDocumentsResponse)
@inject
async def get_compare_result(
    current_user: CurrentUser,
    comparison_id: UUID,
    use_case: FromDishka[GetCompareResultUseCase],
) -> CompareDocumentsResponse:
    result = await use_case(GetCompareResultDTO(user_id=current_user.id, comparison_id=comparison_id))
    return to_compare_documents_response(result)


@router.delete("/results/{comparison_id}", status_code=status.HTTP_204_NO_CONTENT)
@inject
async def delete_compare_result(
    current_user: CurrentUser,
    comparison_id: UUID,
    use_case: FromDishka[DeleteCompareResultUseCase],
) -> Response:
    await use_case(DeleteCompareResultDTO(user_id=current_user.id, comparison_id=comparison_id))
    return Response(status_code=status.HTTP_204_NO_CONTENT)
