from uuid import UUID

from dishka.integrations.fastapi import FromDishka, inject
from fastapi import APIRouter, File, Form, Request, UploadFile, status

from src.application.dtos.ingestion_dtos import IngestDocumentDTO
from src.application.ports.ingestion.file_storage import IFileStorage
from src.application.use_cases.documents.get_document_status_use_case import GetDocumentStatusUseCase
from src.application.use_cases.documents.ingest_document_use_case import IngestDocumentUseCase
from src.core.metrics import metrics_registry
from src.domain.value_objects.document_type import DocumentType
from src.presentation.dependencies.auth import CurrentUser
from src.presentation.middleware.rate_limit import limiter
from src.presentation.schemas.document import (
    DocumentResponse,
    DocumentStatusResponse,
    IngestDocumentRequest,
    IngestTextDocumentRequest,
)

router = APIRouter(tags=["ingestion"])


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
        result = await use_case(
            IngestDocumentDTO(
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
        )
    metrics_registry.inc_counter(
        "cortex_http_requests_total",
        "HTTP requests handled by selected endpoints.",
        labels={"endpoint": "ingest_document", "method": "POST", "status": "202"},
    )
    return DocumentResponse.from_dto(result)


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
    content = await file.read()
    stored_file = await file_storage.save_document_file(
        user_id=current_user.id,
        filename=file.filename or "upload.pdf",
        content=content,
    )
    with metrics_registry.timer(
        "cortex_ingestion_latency_seconds",
        "Latency of ingestion HTTP requests in seconds.",
        labels={"endpoint": "ingest_pdf_document"},
    ):
        result = await use_case(
            IngestDocumentDTO(
                user_id=current_user.id,
                title=title or file.filename or "Uploaded PDF",
                type=DocumentType.PDF,
                collection_id=collection_id,
                file_path=stored_file.path,
                file_size_bytes=stored_file.size_bytes,
                language=language,
            )
        )
    metrics_registry.inc_counter(
        "cortex_http_requests_total",
        "HTTP requests handled by selected endpoints.",
        labels={"endpoint": "ingest_pdf_document", "method": "POST", "status": "202"},
    )
    return DocumentResponse.from_dto(result)


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
    content = await file.read()
    stored_file = await file_storage.save_document_file(
        user_id=current_user.id,
        filename=file.filename or "upload.audio",
        content=content,
    )
    with metrics_registry.timer(
        "cortex_ingestion_latency_seconds",
        "Latency of ingestion HTTP requests in seconds.",
        labels={"endpoint": "ingest_audio_document"},
    ):
        result = await use_case(
            IngestDocumentDTO(
                user_id=current_user.id,
                title=title or file.filename or "Uploaded Audio",
                type=DocumentType.AUDIO,
                collection_id=collection_id,
                file_path=stored_file.path,
                file_size_bytes=stored_file.size_bytes,
                language=language,
            )
        )
    metrics_registry.inc_counter(
        "cortex_http_requests_total",
        "HTTP requests handled by selected endpoints.",
        labels={"endpoint": "ingest_audio_document", "method": "POST", "status": "202"},
    )
    return DocumentResponse.from_dto(result)


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
    content = await file.read()
    stored_file = await file_storage.save_document_file(
        user_id=current_user.id,
        filename=file.filename or "upload.image",
        content=content,
    )
    with metrics_registry.timer(
        "cortex_ingestion_latency_seconds",
        "Latency of ingestion HTTP requests in seconds.",
        labels={"endpoint": "ingest_image_document"},
    ):
        result = await use_case(
            IngestDocumentDTO(
                user_id=current_user.id,
                title=title or file.filename or "Uploaded Image",
                type=DocumentType.IMAGE,
                collection_id=collection_id,
                file_path=stored_file.path,
                file_size_bytes=stored_file.size_bytes,
                language=language,
            )
        )
    metrics_registry.inc_counter(
        "cortex_http_requests_total",
        "HTTP requests handled by selected endpoints.",
        labels={"endpoint": "ingest_image_document", "method": "POST", "status": "202"},
    )
    return DocumentResponse.from_dto(result)


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
        result = await use_case(
            IngestDocumentDTO(
                user_id=current_user.id,
                title=body.title,
                type=body.type,
                collection_id=body.collection_id,
                source_url=body.source_url,
                raw_content=body.raw_text,
                language=body.language,
            )
        )
    metrics_registry.inc_counter(
        "cortex_http_requests_total",
        "HTTP requests handled by selected endpoints.",
        labels={"endpoint": "ingest_text_document", "method": "POST", "status": "202"},
    )
    return DocumentResponse.from_dto(result)


@router.get("/documents/{document_id}/status", response_model=DocumentStatusResponse)
@inject
async def get_document_status(
    document_id: UUID,
    current_user: CurrentUser,
    use_case: FromDishka[GetDocumentStatusUseCase],
) -> DocumentStatusResponse:
    result = await use_case(document_id, current_user.id)
    return DocumentStatusResponse.from_dto(result)
