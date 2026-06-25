from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.documents.activity_repository import DocumentActivityRepository
from src.documents.dependencies import (
    get_document_activity_repository,
    get_document_collection_access,
    get_document_processing_service,
    get_document_repository,
    get_document_status_cache,
    get_task_dispatcher,
)
from src.documents.document_repository import DocumentRepository
from src.documents.ingestion import DocumentIngester
from src.documents.processing import DocumentProcessingService
from src.documents.service import DocumentCollectionAccess, DocumentStatusService
from src.documents.status_cache import RedisDocumentStatusCache
from src.kit.storage.factory import build_file_storage
from src.kit.storage.file_storage import FileStorage
from src.postgres import get_db_session
from src.worker.dispatcher import CeleryTaskDispatcher


def get_document_ingester(
    session: AsyncSession = Depends(get_db_session),
    document_repo: DocumentRepository = Depends(get_document_repository),
    status_cache: RedisDocumentStatusCache = Depends(get_document_status_cache),
    task_dispatcher: CeleryTaskDispatcher = Depends(get_task_dispatcher),
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
    status_cache: RedisDocumentStatusCache = Depends(get_document_status_cache),
) -> DocumentStatusService:
    return DocumentStatusService(document_repo, status_cache)


def get_file_storage() -> FileStorage:
    return build_file_storage()
