from uuid import UUID

from dishka.integrations.fastapi import FromDishka, inject
from fastapi import APIRouter, Query, Response, status

from src.application.use_cases.documents.create_document_use_case import CreateDocumentUseCase
from src.application.use_cases.documents.delete_document_use_case import DeleteDocumentUseCase
from src.application.use_cases.documents.get_document_use_case import GetDocumentUseCase
from src.application.use_cases.documents.list_documents_use_case import ListDocumentsUseCase
from src.application.use_cases.documents.reprocess_document_use_case import ReprocessDocumentUseCase
from src.application.use_cases.documents.retry_document_use_case import RetryDocumentUseCase
from src.presentation.dependencies.auth import CurrentUser
from src.presentation.mappers.document_mapper import to_document_list_response, to_document_response
from src.presentation.mappers.document_request_mapper import (
    to_create_document_dto,
    to_delete_document_dto,
    to_get_document_dto,
    to_list_documents_dto,
    to_reprocess_document_dto,
    to_retry_document_dto,
)
from src.presentation.schemas.document import CreateDocumentRequest, DocumentListResponse, DocumentResponse

router = APIRouter(prefix="/documents", tags=["documents"])


@router.post("", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
@inject
async def create_document(
    body: CreateDocumentRequest,
    current_user: CurrentUser,
    use_case: FromDishka[CreateDocumentUseCase],
) -> DocumentResponse:
    result = await use_case(to_create_document_dto(body, current_user.id))
    return to_document_response(result)


@router.get("", response_model=DocumentListResponse)
@inject
async def list_documents(
    current_user: CurrentUser,
    use_case: FromDishka[ListDocumentsUseCase],
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> DocumentListResponse:
    result = await use_case(to_list_documents_dto(current_user.id, limit, offset))
    return to_document_list_response(result)


@router.get("/{document_id}", response_model=DocumentResponse)
@inject
async def get_document(
    document_id: UUID,
    current_user: CurrentUser,
    use_case: FromDishka[GetDocumentUseCase],
) -> DocumentResponse:
    result = await use_case(to_get_document_dto(document_id, current_user.id))
    return to_document_response(result)


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
@inject
async def delete_document(
    document_id: UUID,
    current_user: CurrentUser,
    use_case: FromDishka[DeleteDocumentUseCase],
) -> Response:
    await use_case(to_delete_document_dto(document_id, current_user.id))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{document_id}/retry", response_model=DocumentResponse)
@inject
async def retry_document(
    document_id: UUID,
    current_user: CurrentUser,
    use_case: FromDishka[RetryDocumentUseCase],
) -> DocumentResponse:
    result = await use_case(to_retry_document_dto(document_id, current_user.id))
    return to_document_response(result)


@router.post("/{document_id}/reprocess", response_model=DocumentResponse)
@inject
async def reprocess_document(
    document_id: UUID,
    current_user: CurrentUser,
    use_case: FromDishka[ReprocessDocumentUseCase],
) -> DocumentResponse:
    result = await use_case(to_reprocess_document_dto(document_id, current_user.id))
    return to_document_response(result)
