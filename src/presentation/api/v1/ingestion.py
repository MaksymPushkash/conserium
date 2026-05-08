from uuid import UUID

from dishka.integrations.fastapi import FromDishka, inject
from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile, status

from src.application.dtos.document_dtos import DocumentDTO
from src.application.ports.ingestion.file_storage import IFileStorage
from src.application.use_cases.documents.get_document_status_use_case import GetDocumentStatusUseCase
from src.application.use_cases.documents.ingest_document_use_case import IngestDocumentUseCase
from src.core.config import settings
from src.core.metrics import metrics_registry
from src.domain.value_objects.document_type import DocumentType
from src.presentation.dependencies.auth import CurrentUser
from src.presentation.mappers.document_mapper import to_document_response, to_document_status_response
from src.presentation.mappers.document_request_mapper import (
    to_ingest_document_dto,
    to_ingest_text_document_dto,
    to_uploaded_ingest_document_dto,
)
from src.presentation.middleware.rate_limit import limiter
from src.presentation.schemas.document import (
    DocumentResponse,
    DocumentStatusResponse,
    IngestDocumentRequest,
    IngestTextDocumentRequest,
)

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
@inject
async def ingest_document(
    request: Request,
    body: IngestDocumentRequest,
    current_user: CurrentUser,
    use_case: FromDishka[IngestDocumentUseCase],
) -> DocumentResponse:
    with metrics_registry.timer(
        "cortex_ingestion_latency_seconds",
        "Latency of ingestion HTTP requests in seconds.",
        labels={"endpoint": "ingest_document"},
    ):
        result = await use_case(to_ingest_document_dto(body, current_user.id))
    metrics_registry.inc_counter(
        "cortex_http_requests_total",
        "HTTP requests handled by selected endpoints.",
        labels={"endpoint": "ingest_document", "method": "POST", "status": "202"},
    )
    return to_document_response(result)


@router.post(
    "/documents/ingest/pdf",
    response_model=DocumentResponse,
    status_code=status.HTTP_202_ACCEPTED,
    deprecated=True,
)
@router.post("/ingest/pdf", response_model=DocumentResponse, status_code=status.HTTP_202_ACCEPTED)
@inject
async def ingest_pdf_document(
    current_user: CurrentUser,
    use_case: FromDishka[IngestDocumentUseCase],
    file_storage: FromDishka[IFileStorage],
    file: UploadFile = File(...),
    title: str | None = Form(default=None),
    collection_id: UUID | None = Form(default=None),
    language: str | None = Form(default=None),
) -> DocumentResponse:
    result = await _ingest_uploaded_file(
        current_user=current_user,
        use_case=use_case,
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
    "/documents/ingest/audio",
    response_model=DocumentResponse,
    status_code=status.HTTP_202_ACCEPTED,
    deprecated=True,
)
@router.post("/ingest/audio", response_model=DocumentResponse, status_code=status.HTTP_202_ACCEPTED)
@inject
async def ingest_audio_document(
    current_user: CurrentUser,
    use_case: FromDishka[IngestDocumentUseCase],
    file_storage: FromDishka[IFileStorage],
    file: UploadFile = File(...),
    title: str | None = Form(default=None),
    collection_id: UUID | None = Form(default=None),
    language: str | None = Form(default=None),
) -> DocumentResponse:
    result = await _ingest_uploaded_file(
        current_user=current_user,
        use_case=use_case,
        file_storage=file_storage,
        file=file,
        title=title,
        collection_id=collection_id,
        language=language,
        document_type=DocumentType.AUDIO,
        fallback_filename="upload.audio",
        default_title="Uploaded Audio",
        endpoint="ingest_audio_document",
    )
    return to_document_response(result)


@router.post(
    "/documents/ingest/image",
    response_model=DocumentResponse,
    status_code=status.HTTP_202_ACCEPTED,
    deprecated=True,
)
@router.post("/ingest/image", response_model=DocumentResponse, status_code=status.HTTP_202_ACCEPTED)
@inject
async def ingest_image_document(
    current_user: CurrentUser,
    use_case: FromDishka[IngestDocumentUseCase],
    file_storage: FromDishka[IFileStorage],
    file: UploadFile = File(...),
    title: str | None = Form(default=None),
    collection_id: UUID | None = Form(default=None),
    language: str | None = Form(default=None),
) -> DocumentResponse:
    result = await _ingest_uploaded_file(
        current_user=current_user,
        use_case=use_case,
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
@inject
async def ingest_text_document(
    body: IngestTextDocumentRequest,
    current_user: CurrentUser,
    use_case: FromDishka[IngestDocumentUseCase],
) -> DocumentResponse:
    with metrics_registry.timer(
        "cortex_ingestion_latency_seconds",
        "Latency of ingestion HTTP requests in seconds.",
        labels={"endpoint": "ingest_text_document"},
    ):
        result = await use_case(to_ingest_text_document_dto(body, current_user.id))
    metrics_registry.inc_counter(
        "cortex_http_requests_total",
        "HTTP requests handled by selected endpoints.",
        labels={"endpoint": "ingest_text_document", "method": "POST", "status": "202"},
    )
    return to_document_response(result)


@router.get("/documents/{document_id}/status", response_model=DocumentStatusResponse)
@inject
async def get_document_status(
    document_id: UUID,
    current_user: CurrentUser,
    use_case: FromDishka[GetDocumentStatusUseCase],
) -> DocumentStatusResponse:
    result = await use_case(document_id, current_user.id)
    return to_document_status_response(result)


async def _ingest_uploaded_file(
    *,
    current_user: CurrentUser,
    use_case: IngestDocumentUseCase,
    file_storage: IFileStorage,
    file: UploadFile,
    title: str | None,
    collection_id: UUID | None,
    language: str | None,
    document_type: DocumentType,
    fallback_filename: str,
    default_title: str,
    endpoint: str,
) -> DocumentDTO:
    content = await _read_bounded_upload(file)
    stored_file = await file_storage.save_document_file(
        user_id=current_user.id,
        filename=file.filename or fallback_filename,
        content=content,
    )
    with metrics_registry.timer(
        "cortex_ingestion_latency_seconds",
        "Latency of ingestion HTTP requests in seconds.",
        labels={"endpoint": endpoint},
    ):
        result = await use_case(
            to_uploaded_ingest_document_dto(
                user_id=current_user.id,
                title=title or file.filename or default_title,
                document_type=document_type,
                collection_id=collection_id,
                file_path=stored_file.path,
                file_size_bytes=stored_file.size_bytes,
                language=language,
            )
        )
    metrics_registry.inc_counter(
        "cortex_http_requests_total",
        "HTTP requests handled by selected endpoints.",
        labels={"endpoint": endpoint, "method": "POST", "status": "202"},
    )
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
