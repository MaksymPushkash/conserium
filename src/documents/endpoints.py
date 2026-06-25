from uuid import UUID

from fastapi import Depends, Query, Response, status

from src.auth.auth import CurrentUser
from src.documents.dependencies import get_document_service
from src.documents.export_dependencies import get_document_exporter
from src.documents.exports import DocumentExporter
from src.documents.ingestion import (
    DocumentReprocessor,
    DocumentRetryer,
)
from src.documents.ingestion_dependencies import get_document_reprocessor, get_document_retryer
from src.documents.note_dependencies import get_note_service
from src.documents.notes import (
    NoteService,
)
from src.documents.schemas import (
    BulkAddDocumentTagsRequest,
    BulkDocumentOperationRequest,
    BulkMoveDocumentsRequest,
    CreateDocumentRequest,
    CreateNoteRequest,
    DocumentChunkResponse,
    DocumentConnectionsResponse,
    DocumentListResponse,
    DocumentQuestionHistoryResponse,
    DocumentResponse,
    DocumentSearchResponse,
    MoveDocumentRequest,
    NoteListResponse,
    NoteResponse,
    NoteVersionResponse,
    RenameDocumentRequest,
    UpdateNoteRequest,
)
from src.documents.service import (
    DocumentService,
    to_document_connections_response,
    to_document_list_response,
    to_document_response,
    to_document_search_response,
)
from src.documents.status import DocumentStatus
from src.documents.types import DocumentType
from src.routing import APIRouter

router = APIRouter()
documents_router = APIRouter(prefix="/documents", tags=["documents"])
notes_router = APIRouter(prefix="/notes", tags=["notes"])


@documents_router.post("", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
async def create_document(
    body: CreateDocumentRequest,
    current_user: CurrentUser,
    service: DocumentService = Depends(get_document_service),
) -> DocumentResponse:
    result = await service.create(user_id=current_user.id, body=body)
    return to_document_response(result)


@documents_router.get("", response_model=DocumentListResponse)
async def list_documents(
    current_user: CurrentUser,
    service: DocumentService = Depends(get_document_service),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    collection_id: UUID | None = Query(default=None),
    document_status: DocumentStatus | None = Query(default=None, alias="status"),
    document_type: DocumentType | None = Query(default=None, alias="type"),
    tag: str | None = Query(default=None, min_length=1, max_length=100),
) -> DocumentListResponse:
    result = await service.list(
        user_id=current_user.id,
        limit=limit,
        offset=offset,
        collection_id=collection_id,
        status=document_status,
        document_type=document_type,
        tag_name=tag,
    )
    return to_document_list_response(result)


@documents_router.get("/search", response_model=DocumentSearchResponse)
async def search_documents(
    current_user: CurrentUser,
    service: DocumentService = Depends(get_document_service),
    query: str = Query(min_length=1, max_length=500),
    limit: int = Query(default=20, ge=1, le=50),
    collection_id: UUID | None = Query(default=None),
    document_status: DocumentStatus | None = Query(default=None, alias="status"),
    document_type: DocumentType | None = Query(default=None, alias="type"),
    tag: str | None = Query(default=None, min_length=1, max_length=100),
) -> DocumentSearchResponse:
    result = await service.search(
        user_id=current_user.id,
        query=query,
        limit=limit,
        collection_id=collection_id,
        status=document_status,
        document_type=document_type,
        tag_name=tag,
    )
    return to_document_search_response(result)


@documents_router.get("/{document_id}", response_model=DocumentResponse)
async def get_document(
    document_id: UUID,
    current_user: CurrentUser,
    service: DocumentService = Depends(get_document_service),
) -> DocumentResponse:
    result = await service.get(user_id=current_user.id, document_id=document_id)
    return to_document_response(result)


@documents_router.get("/{document_id}/suggested-questions", response_model=list[str])
async def get_document_suggested_questions(
    document_id: UUID,
    current_user: CurrentUser,
    service: DocumentService = Depends(get_document_service),
) -> list[str]:
    result = await service.get(user_id=current_user.id, document_id=document_id)
    return result.suggested_questions or []


@documents_router.get("/{document_id}/connections", response_model=DocumentConnectionsResponse)
async def get_document_connections(
    document_id: UUID,
    current_user: CurrentUser,
    service: DocumentService = Depends(get_document_service),
    limit: int = Query(default=5, ge=1, le=20),
) -> DocumentConnectionsResponse:
    result = await service.connections(user_id=current_user.id, document_id=document_id, limit=limit)
    return to_document_connections_response(result)


@documents_router.get("/{document_id}/export")
async def export_document(
    document_id: UUID,
    current_user: CurrentUser,
    handler: DocumentExporter = Depends(get_document_exporter),
    export_format: str = Query(default="markdown", alias="format", pattern="^(markdown|md|pdf)$"),
) -> Response:
    result = await handler(user_id=current_user.id, document_id=document_id, export_format=export_format)
    return Response(
        content=result.content,
        media_type=result.media_type,
        headers={"Content-Disposition": f'attachment; filename="{result.filename}"'},
    )


@documents_router.get("/{document_id}/chunks/{chunk_id}", response_model=DocumentChunkResponse)
async def get_document_chunk(
    document_id: UUID,
    chunk_id: UUID,
    current_user: CurrentUser,
    service: DocumentService = Depends(get_document_service),
) -> DocumentChunkResponse:
    result = await service.chunk(user_id=current_user.id, document_id=document_id, chunk_id=chunk_id)
    return result


@documents_router.get("/{document_id}/questions", response_model=DocumentQuestionHistoryResponse)
async def get_document_question_history(
    document_id: UUID,
    current_user: CurrentUser,
    service: DocumentService = Depends(get_document_service),
    limit: int = Query(default=5, ge=1, le=20),
) -> DocumentQuestionHistoryResponse:
    result = await service.question_history(user_id=current_user.id, document_id=document_id, limit=limit)
    return result


@documents_router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    document_id: UUID,
    current_user: CurrentUser,
    service: DocumentService = Depends(get_document_service),
) -> Response:
    await service.delete(user_id=current_user.id, document_id=document_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@documents_router.patch("/{document_id}", response_model=DocumentResponse)
async def rename_document(
    document_id: UUID,
    body: RenameDocumentRequest,
    current_user: CurrentUser,
    service: DocumentService = Depends(get_document_service),
) -> DocumentResponse:
    result = await service.rename(user_id=current_user.id, document_id=document_id, body=body)
    return to_document_response(result)


@documents_router.patch("/{document_id}/collection", response_model=DocumentResponse)
async def move_document(
    document_id: UUID,
    body: MoveDocumentRequest,
    current_user: CurrentUser,
    service: DocumentService = Depends(get_document_service),
) -> DocumentResponse:
    result = await service.move(user_id=current_user.id, document_id=document_id, body=body)
    return to_document_response(result)


@documents_router.post("/bulk/delete", status_code=status.HTTP_204_NO_CONTENT)
async def bulk_delete_documents(
    body: BulkDocumentOperationRequest,
    current_user: CurrentUser,
    service: DocumentService = Depends(get_document_service),
) -> Response:
    await service.bulk_delete(user_id=current_user.id, document_ids=body.document_ids)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@documents_router.post("/bulk/move", status_code=status.HTTP_204_NO_CONTENT)
async def bulk_move_documents(
    body: BulkMoveDocumentsRequest,
    current_user: CurrentUser,
    service: DocumentService = Depends(get_document_service),
) -> Response:
    await service.bulk_move(user_id=current_user.id, document_ids=body.document_ids, collection_id=body.collection_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@documents_router.post("/bulk/tags", status_code=status.HTTP_204_NO_CONTENT)
async def bulk_add_document_tags(
    body: BulkAddDocumentTagsRequest,
    current_user: CurrentUser,
    service: DocumentService = Depends(get_document_service),
) -> Response:
    await service.bulk_add_tags(user_id=current_user.id, body=body)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@documents_router.post("/bulk/reprocess", status_code=status.HTTP_202_ACCEPTED)
async def bulk_reprocess_documents(
    body: BulkDocumentOperationRequest,
    current_user: CurrentUser,
    service: DocumentService = Depends(get_document_service),
) -> Response:
    await service.bulk_reprocess(user_id=current_user.id, document_ids=body.document_ids)
    return Response(status_code=status.HTTP_202_ACCEPTED)


@documents_router.post("/{document_id}/retry", response_model=DocumentResponse)
async def retry_document(
    document_id: UUID,
    current_user: CurrentUser,
    handler: DocumentRetryer = Depends(get_document_retryer),
) -> DocumentResponse:
    result = await handler(user_id=current_user.id, document_id=document_id)
    return to_document_response(result)


@documents_router.post("/{document_id}/reprocess", response_model=DocumentResponse)
async def reprocess_document(
    document_id: UUID,
    current_user: CurrentUser,
    handler: DocumentReprocessor = Depends(get_document_reprocessor),
) -> DocumentResponse:
    result = await handler(user_id=current_user.id, document_id=document_id)
    return to_document_response(result)


@notes_router.post("", response_model=NoteResponse, status_code=status.HTTP_201_CREATED)
async def create_note(
    body: CreateNoteRequest,
    current_user: CurrentUser,
    service: NoteService = Depends(get_note_service),
) -> NoteResponse:
    result = await service.create(user_id=current_user.id, body=body)
    return result


@notes_router.get("", response_model=NoteListResponse)
async def list_notes(
    current_user: CurrentUser,
    service: NoteService = Depends(get_note_service),
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    collection_id: UUID | None = Query(default=None),
) -> NoteListResponse:
    result = await service.list(user_id=current_user.id, limit=limit, offset=offset, collection_id=collection_id)
    return result


@notes_router.get("/{note_id}", response_model=NoteResponse)
async def get_note(
    note_id: UUID,
    current_user: CurrentUser,
    service: NoteService = Depends(get_note_service),
) -> NoteResponse:
    result = await service.get(user_id=current_user.id, note_id=note_id)
    return result


@notes_router.get("/{note_id}/versions", response_model=list[NoteVersionResponse])
async def list_note_versions(
    note_id: UUID,
    current_user: CurrentUser,
    service: NoteService = Depends(get_note_service),
) -> list[NoteVersionResponse]:
    result = await service.list_versions(user_id=current_user.id, note_id=note_id)
    return list(result)


@notes_router.patch("/{note_id}", response_model=NoteResponse)
async def update_note(
    note_id: UUID,
    body: UpdateNoteRequest,
    current_user: CurrentUser,
    service: NoteService = Depends(get_note_service),
) -> NoteResponse:
    result = await service.update(user_id=current_user.id, note_id=note_id, body=body)
    return result


@notes_router.post("/{note_id}/versions/{version_id}/restore", response_model=NoteResponse)
async def restore_note_version(
    note_id: UUID,
    version_id: UUID,
    current_user: CurrentUser,
    service: NoteService = Depends(get_note_service),
) -> NoteResponse:
    result = await service.restore_version(user_id=current_user.id, note_id=note_id, version_id=version_id)
    return result


@notes_router.delete("/{note_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_note(
    note_id: UUID,
    current_user: CurrentUser,
    service: NoteService = Depends(get_note_service),
) -> Response:
    await service.delete(user_id=current_user.id, note_id=note_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


router.include_router(documents_router)
router.include_router(notes_router)

__all__ = ["router"]
