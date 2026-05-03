from uuid import UUID

from dishka.integrations.fastapi import FromDishka, inject
from fastapi import APIRouter, Query, Response, status

from src.application.dtos.document_dtos import CreateDocumentDTO, DeleteDocumentDTO, GetDocumentDTO, ListDocumentsDTO
from src.application.use_cases.documents.create_document_use_case import CreateDocumentUseCase
from src.application.use_cases.documents.delete_document_use_case import DeleteDocumentUseCase
from src.application.use_cases.documents.get_document_use_case import GetDocumentUseCase
from src.application.use_cases.documents.list_documents_use_case import ListDocumentsUseCase
from src.presentation.dependencies.auth import CurrentUser
from src.presentation.schemas.document import CreateDocumentRequest, DocumentListResponse, DocumentResponse

router = APIRouter(prefix="/documents", tags=["documents"])


@router.post("", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
@inject
async def create_document(
    body: CreateDocumentRequest,
    current_user: CurrentUser,
    use_case: FromDishka[CreateDocumentUseCase],
) -> DocumentResponse:
    result = await use_case(
        CreateDocumentDTO(
            user_id=current_user.id,
            title=body.title,
            type=body.type,
            collection_id=body.collection_id,
            source_url=body.source_url,
            file_path=body.file_path,
            file_size_bytes=body.file_size_bytes,
            raw_content=body.raw_content,
            summary=body.summary,
            word_count=body.word_count,
            language=body.language,
        )
    )
    return DocumentResponse.from_dto(result)


@router.get("", response_model=DocumentListResponse)
@inject
async def list_documents(
    current_user: CurrentUser,
    use_case: FromDishka[ListDocumentsUseCase],
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> DocumentListResponse:
    result = await use_case(
        ListDocumentsDTO(
            user_id=current_user.id,
            limit=limit,
            offset=offset,
        )
    )
    return DocumentListResponse.from_dto(result)


@router.get("/{document_id}", response_model=DocumentResponse)
@inject
async def get_document(
    document_id: UUID,
    current_user: CurrentUser,
    use_case: FromDishka[GetDocumentUseCase],
) -> DocumentResponse:
    result = await use_case(
        GetDocumentDTO(
            user_id=current_user.id,
            document_id=document_id,
        )
    )
    return DocumentResponse.from_dto(result)


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
@inject
async def delete_document(
    document_id: UUID,
    current_user: CurrentUser,
    use_case: FromDishka[DeleteDocumentUseCase],
) -> Response:
    await use_case(
        DeleteDocumentDTO(
            user_id=current_user.id,
            document_id=document_id,
        )
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
