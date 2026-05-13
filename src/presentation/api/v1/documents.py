from uuid import UUID

from dishka.integrations.fastapi import FromDishka, inject
from fastapi import APIRouter, Query, Response, status

from src.application.use_cases.documents.create_document_use_case import CreateDocumentUseCase
from src.application.use_cases.documents.delete_document_use_case import DeleteDocumentUseCase
from src.application.use_cases.documents.get_document_chunk_use_case import GetDocumentChunkUseCase
from src.application.use_cases.documents.get_document_use_case import GetDocumentUseCase
from src.application.use_cases.documents.list_documents_use_case import ListDocumentsUseCase
from src.application.use_cases.documents.manage_document_use_cases import (
    BulkDeleteDocumentsUseCase,
    BulkReprocessDocumentsUseCase,
    MoveDocumentUseCase,
    RenameDocumentUseCase,
)
from src.application.use_cases.documents.reprocess_document_use_case import ReprocessDocumentUseCase
from src.application.use_cases.documents.retry_document_use_case import RetryDocumentUseCase
from src.domain.value_objects.document_status import DocumentStatus
from src.presentation.dependencies.auth import CurrentUser
from src.presentation.mappers.document_mapper import (
    to_document_chunk_response,
    to_document_list_response,
    to_document_response,
)
from src.presentation.mappers.document_request_mapper import (
    to_bulk_document_operation_dto,
    to_create_document_dto,
    to_delete_document_dto,
    to_get_document_chunk_dto,
    to_get_document_dto,
    to_list_documents_dto,
    to_move_document_dto,
    to_rename_document_dto,
    to_reprocess_document_dto,
    to_retry_document_dto,
)
from src.presentation.schemas.document import (
    BulkDocumentOperationRequest,
    CreateDocumentRequest,
    DocumentChunkResponse,
    DocumentListResponse,
    DocumentResponse,
    MoveDocumentRequest,
    RenameDocumentRequest,
)

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
    collection_id: UUID | None = Query(default=None),
    document_status: DocumentStatus | None = Query(default=None, alias="status"),
) -> DocumentListResponse:
    result = await use_case(to_list_documents_dto(current_user.id, limit, offset, collection_id, document_status))
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


@router.get("/{document_id}/chunks/{chunk_id}", response_model=DocumentChunkResponse)
@inject
async def get_document_chunk(
    document_id: UUID,
    chunk_id: UUID,
    current_user: CurrentUser,
    use_case: FromDishka[GetDocumentChunkUseCase],
) -> DocumentChunkResponse:
    result = await use_case(to_get_document_chunk_dto(document_id, chunk_id, current_user.id))
    return to_document_chunk_response(result)


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
@inject
async def delete_document(
    document_id: UUID,
    current_user: CurrentUser,
    use_case: FromDishka[DeleteDocumentUseCase],
) -> Response:
    await use_case(to_delete_document_dto(document_id, current_user.id))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.patch("/{document_id}", response_model=DocumentResponse)
@inject
async def rename_document(
    document_id: UUID,
    body: RenameDocumentRequest,
    current_user: CurrentUser,
    use_case: FromDishka[RenameDocumentUseCase],
) -> DocumentResponse:
    result = await use_case(to_rename_document_dto(document_id, body.title, current_user.id))
    return to_document_response(result)


@router.patch("/{document_id}/collection", response_model=DocumentResponse)
@inject
async def move_document(
    document_id: UUID,
    body: MoveDocumentRequest,
    current_user: CurrentUser,
    use_case: FromDishka[MoveDocumentUseCase],
) -> DocumentResponse:
    result = await use_case(to_move_document_dto(document_id, body.collection_id, current_user.id))
    return to_document_response(result)


@router.post("/bulk/delete", status_code=status.HTTP_204_NO_CONTENT)
@inject
async def bulk_delete_documents(
    body: BulkDocumentOperationRequest,
    current_user: CurrentUser,
    use_case: FromDishka[BulkDeleteDocumentsUseCase],
) -> Response:
    await use_case(to_bulk_document_operation_dto(body.document_ids, current_user.id))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/bulk/reprocess", status_code=status.HTTP_202_ACCEPTED)
@inject
async def bulk_reprocess_documents(
    body: BulkDocumentOperationRequest,
    current_user: CurrentUser,
    use_case: FromDishka[BulkReprocessDocumentsUseCase],
) -> Response:
    await use_case(to_bulk_document_operation_dto(body.document_ids, current_user.id))
    return Response(status_code=status.HTTP_202_ACCEPTED)


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
