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
from src.documents.external_intake_repository import ExternalIntakeRepository
from src.documents.ingestion import (
    DocumentIngester,
    DocumentReprocessor,
    DocumentRetryer,
    ExternalIntakeService,
    ExternalItemIngester,
)
from src.documents.processing import DocumentProcessingService
from src.documents.service import DocumentCollectionAccess
from src.documents.status_cache import RedisDocumentStatusCache
from src.postgres import get_db_session
from src.worker.dispatcher import CeleryTaskDispatcher


def get_document_retryer(
    document_repo: DocumentRepository = Depends(get_document_repository),
    processing_service: DocumentProcessingService = Depends(get_document_processing_service),
) -> DocumentRetryer:
    return DocumentRetryer(document_repo, processing_service)


def get_document_reprocessor(
    document_repo: DocumentRepository = Depends(get_document_repository),
    processing_service: DocumentProcessingService = Depends(get_document_processing_service),
) -> DocumentReprocessor:
    return DocumentReprocessor(document_repo, processing_service)


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


def get_external_item_ingester(
    session: AsyncSession = Depends(get_db_session),
    ingest_document: DocumentIngester = Depends(get_document_ingester),
) -> ExternalItemIngester:
    return ExternalItemIngester(
        session,
        ExternalIntakeRepository.from_session(session),
        DocumentRepository.from_session(session),
        ingest_document,
    )


def get_external_intake_service(
    session: AsyncSession = Depends(get_db_session),
    ingest_document: DocumentIngester = Depends(get_document_ingester),
) -> ExternalIntakeService:
    return ExternalIntakeService(
        session,
        ExternalIntakeRepository.from_session(session),
        DocumentRepository.from_session(session),
        ingest_document,
    )
