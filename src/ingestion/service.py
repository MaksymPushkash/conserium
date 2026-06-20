from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import Depends

from src.documents.dependencies import (
    get_document_activity_repository,
    get_document_collection_access,
    get_document_processing_service,
    get_document_repository,
    get_document_status_cache,
    get_task_dispatcher,
)
from src.documents.ingestion import DocumentIngester
from src.documents.schemas import IngestDocumentDTO, IngestDocumentRequest, IngestTextDocumentRequest
from src.documents.service import (
    DocumentCollectionAccess,
    DocumentStatusService,
)
from src.kit.storage.factory import build_file_storage
from src.postgres import AsyncSession, get_db_session

if TYPE_CHECKING:
    from uuid import UUID

    from src.documents.activity_repository import DocumentActivityRepository
    from src.documents.document_repository import DocumentRepository
    from src.documents.processing import DocumentProcessingService
    from src.documents.status_cache import IDocumentStatusCache
    from src.documents.types import DocumentType
    from src.kit.ports.ingestion.file_storage import IFileStorage
    from src.worker.dispatcher import ITaskDispatcher


def get_document_ingester(
    session: AsyncSession = Depends(get_db_session),
    document_repo: DocumentRepository = Depends(get_document_repository),
    status_cache: IDocumentStatusCache = Depends(get_document_status_cache),
    task_dispatcher: ITaskDispatcher = Depends(get_task_dispatcher),
    collection_access: DocumentCollectionAccess = Depends(get_document_collection_access),
    activity_repo: DocumentActivityRepository = Depends(get_document_activity_repository),
    processing_service: DocumentProcessingService = Depends(get_document_processing_service),
) -> DocumentIngester:
    return DocumentIngester(
        session,
        document_repo,
        status_cache,
        task_dispatcher,
        collection_access,
        activity_repo,
        processing_service,
    )


def get_document_status_service(
    document_repo: DocumentRepository = Depends(get_document_repository),
    status_cache: IDocumentStatusCache = Depends(get_document_status_cache),
) -> DocumentStatusService:
    return DocumentStatusService(document_repo, status_cache)


def get_file_storage() -> IFileStorage:
    return build_file_storage()


def to_ingest_document_dto(body: IngestDocumentRequest, user_id: UUID) -> IngestDocumentDTO:
    return IngestDocumentDTO(
        user_id=user_id,
        title=body.title,
        type=body.type,
        collection_id=body.collection_id,
        source_url=body.source_url,
        file_path=body.file_path,
        file_size_bytes=body.file_size_bytes,
        raw_content=body.raw_content,
        language=body.language,
    )


def to_ingest_text_document_dto(body: IngestTextDocumentRequest, user_id: UUID) -> IngestDocumentDTO:
    return IngestDocumentDTO(
        user_id=user_id,
        title=body.title,
        type=body.type,
        collection_id=body.collection_id,
        source_url=body.source_url,
        raw_content=body.raw_text,
        language=body.language,
    )


def to_uploaded_ingest_document_dto(
    *,
    user_id: UUID,
    title: str,
    document_type: DocumentType,
    collection_id: UUID | None,
    file_path: str,
    file_size_bytes: int,
    language: str | None,
) -> IngestDocumentDTO:
    return IngestDocumentDTO(
        user_id=user_id,
        title=title,
        type=document_type,
        collection_id=collection_id,
        file_path=file_path,
        file_size_bytes=file_size_bytes,
        language=language,
    )


__all__ = [
    "get_document_ingester",
    "get_document_status_service",
    "get_file_storage",
    "to_ingest_document_dto",
    "to_ingest_text_document_dto",
    "to_uploaded_ingest_document_dto",
]
