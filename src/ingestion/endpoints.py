from uuid import UUID

from fastapi import Depends, File, Form, HTTPException, Request, UploadFile, status

from src.auth.auth import CurrentUser
from src.documents.ingestion import DocumentIngester
from src.documents.schemas import (
    DocumentResponse,
    DocumentResult,
    DocumentStatusResponse,
    IngestDocumentRequest,
    IngestTextDocumentRequest,
)
from src.documents.service import to_document_response
from src.documents.status_service import DocumentStatusService, to_document_status_response
from src.documents.types import DocumentType
from src.ingestion.dependencies import get_document_ingester, get_document_status_service, get_file_storage
from src.kit.storage.file_storage import FileStorage
from src.observability.metrics import ingestion_latency_timer, record_http_request
from src.observability.rate_limit import limiter
from src.routing import APIRouter
from src.settings import settings

router = APIRouter(tags=["ingestion"])
UPLOAD_READ_CHUNK_BYTES = 1024 * 1024


@router.post(
    "/documents/ingest",
    response_model=DocumentResponse,
    status_code=status.HTTP_202_ACCEPTED,
    deprecated=True,
)
@router.post("/ingest", response_model=DocumentResponse, status_code=status.HTTP_202_ACCEPTED)
@limiter.limit("50/minute")
async def ingest_document(
    request: Request,
    body: IngestDocumentRequest,
    current_user: CurrentUser,
    handler: DocumentIngester = Depends(get_document_ingester),
) -> DocumentResponse:
    with ingestion_latency_timer("ingest_document"):
        result = await handler(
            user_id=current_user.id,
            title=body.title,
            type=body.type,
            collection_id=body.collection_id,
            source_url=body.source_url,
            file_path=body.file_path,
            file_size_bytes=body.file_size_bytes,
            raw_content=body.raw_content,
            language=body.language,
        )
    record_http_request("ingest_document", status="202")
    return to_document_response(result)


@router.post(
    "/documents/ingest/pdf",
    response_model=DocumentResponse,
    status_code=status.HTTP_202_ACCEPTED,
    deprecated=True,
)
@router.post("/ingest/pdf", response_model=DocumentResponse, status_code=status.HTTP_202_ACCEPTED)
@limiter.limit("20/minute")
async def ingest_pdf_document(
    request: Request,
    current_user: CurrentUser,
    handler: DocumentIngester = Depends(get_document_ingester),
    file_storage: FileStorage = Depends(get_file_storage),
    file: UploadFile = File(...),
    title: str | None = Form(default=None),
    collection_id: UUID | None = Form(default=None),
    language: str | None = Form(default=None),
) -> DocumentResponse:
    result = await _ingest_uploaded_file(
        current_user=current_user,
        handler=handler,
        file_storage=file_storage,
        file=file,
        title=title,
        collection_id=collection_id,
        language=language,
        document_type=DocumentType.PDF,
        fallback_filename="upload.pdf",
        default_title="Uploaded PDF",
        endpoint="ingest_pdf_document",
    )
    return to_document_response(result)


@router.post(
    "/documents/ingest/image",
    response_model=DocumentResponse,
    status_code=status.HTTP_202_ACCEPTED,
    deprecated=True,
)
@router.post("/ingest/image", response_model=DocumentResponse, status_code=status.HTTP_202_ACCEPTED)
@limiter.limit("20/minute")
async def ingest_image_document(
    request: Request,
    current_user: CurrentUser,
    handler: DocumentIngester = Depends(get_document_ingester),
    file_storage: FileStorage = Depends(get_file_storage),
    file: UploadFile = File(...),
    title: str | None = Form(default=None),
    collection_id: UUID | None = Form(default=None),
    language: str | None = Form(default=None),
) -> DocumentResponse:
    result = await _ingest_uploaded_file(
        current_user=current_user,
        handler=handler,
        file_storage=file_storage,
        file=file,
        title=title,
        collection_id=collection_id,
        language=language,
        document_type=DocumentType.IMAGE,
        fallback_filename="upload.image",
        default_title="Uploaded Image",
        endpoint="ingest_image_document",
    )
    return to_document_response(result)


@router.post(
    "/documents/ingest-text",
    response_model=DocumentResponse,
    status_code=status.HTTP_202_ACCEPTED,
    deprecated=True,
)
async def ingest_text_document(
    body: IngestTextDocumentRequest,
    current_user: CurrentUser,
    handler: DocumentIngester = Depends(get_document_ingester),
) -> DocumentResponse:
    with ingestion_latency_timer("ingest_text_document"):
        result = await handler(
            user_id=current_user.id,
            title=body.title,
            type=body.type,
            collection_id=body.collection_id,
            source_url=body.source_url,
            raw_content=body.raw_text,
            language=body.language,
        )
    record_http_request("ingest_text_document", status="202")
    return to_document_response(result)


@router.get("/documents/{document_id}/status", response_model=DocumentStatusResponse)
async def get_document_status(
    document_id: UUID,
    current_user: CurrentUser,
    service: DocumentStatusService = Depends(get_document_status_service),
) -> DocumentStatusResponse:
    result = await service.get(document_id, current_user.id)
    return to_document_status_response(result)


async def _ingest_uploaded_file(
    *,
    current_user: CurrentUser,
    handler: DocumentIngester,
    file_storage: FileStorage,
    file: UploadFile,
    title: str | None,
    collection_id: UUID | None,
    language: str | None,
    document_type: DocumentType,
    fallback_filename: str,
    default_title: str,
    endpoint: str,
) -> DocumentResult:
    content = await _read_bounded_upload(file)
    stored_file = await file_storage.save_document_file(
        user_id=current_user.id,
        filename=file.filename or fallback_filename,
        content=content,
    )
    with ingestion_latency_timer(endpoint):
        result = await handler(
            user_id=current_user.id,
            title=title or file.filename or default_title,
            type=document_type,
            collection_id=collection_id,
            file_path=stored_file.path,
            file_size_bytes=stored_file.size_bytes,
            language=language,
        )
    record_http_request(endpoint, status="202")
    return result


async def _read_bounded_upload(file: UploadFile) -> bytes:
    total = 0
    chunks: list[bytes] = []
    while chunk := await file.read(UPLOAD_READ_CHUNK_BYTES):
        total += len(chunk)
        if total > settings.MAX_UPLOAD_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                detail=f"uploaded file exceeds maximum size of {settings.MAX_UPLOAD_BYTES} bytes",
            )
        chunks.append(chunk)
    return b"".join(chunks)


__all__ = ["router"]
