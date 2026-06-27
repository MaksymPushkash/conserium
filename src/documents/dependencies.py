from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import BackgroundTasks, Depends

from src.collections.repository import CollectionRepository
from src.documents.activity_repository import DocumentActivityRepository
from src.documents.chunk_repository import ChunkRepository
from src.documents.document_repository import DocumentRepository
from src.documents.processing import DocumentProcessingService
from src.documents.processing_outbox_repository import DocumentProcessingOutboxRepository
from src.documents.service import (
    DocumentCollectionAccess,
    DocumentService,
)
from src.documents.status_cache import (
    RedisDocumentStatusCache,
)
from src.kit.ai.providers.cached_embedding_provider import CachedEmbeddingProvider
from src.kit.ai.providers.openai_embedding_provider import OpenAIEmbeddingProvider
from src.kit.cache.redis import get_redis
from src.kit.cache.redis_cache import RedisCache
from src.kit.storage.factory import build_file_storage
from src.postgres import AsyncSession, get_db_session
from src.query.repository import SearchQueryRepository
from src.worker.dispatcher import CeleryTaskDispatcher
from src.workspaces.repository import SharedWorkspaceRepository

if TYPE_CHECKING:
    from redis.asyncio import Redis

    from src.kit.ai.embedding_provider import EmbeddingProvider
    from src.kit.storage.file_storage import FileStorage


def get_cache(redis: Redis = Depends(get_redis)) -> RedisCache:
    return RedisCache(redis)


def get_document_repository(session: AsyncSession = Depends(get_db_session)) -> DocumentRepository:
    return DocumentRepository.from_session(session)


def get_document_status_cache(redis: Redis = Depends(get_redis)) -> RedisDocumentStatusCache:
    return RedisDocumentStatusCache(redis)


def get_task_dispatcher() -> CeleryTaskDispatcher:
    return CeleryTaskDispatcher()


def get_embedding_provider(cache: RedisCache = Depends(get_cache)) -> EmbeddingProvider:
    return CachedEmbeddingProvider(OpenAIEmbeddingProvider(), cache)


def get_shared_workspace_repository(session: AsyncSession = Depends(get_db_session)) -> SharedWorkspaceRepository:
    return SharedWorkspaceRepository.from_session(session)


def get_document_activity_repository(
    session: AsyncSession = Depends(get_db_session),
) -> DocumentActivityRepository:
    return DocumentActivityRepository.from_session(session)


def get_chunk_repository(session: AsyncSession = Depends(get_db_session)) -> ChunkRepository:
    return ChunkRepository.from_session(session)


def get_document_processing_service(
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_db_session),
    status_cache: RedisDocumentStatusCache = Depends(get_document_status_cache),
    task_dispatcher: CeleryTaskDispatcher = Depends(get_task_dispatcher),
) -> DocumentProcessingService:
    return DocumentProcessingService(
        session,
        DocumentRepository.from_session(session),
        DocumentProcessingOutboxRepository.from_session(session),
        status_cache,
        task_dispatcher,
        background_tasks,
    )


def build_document_collection_access(session: AsyncSession) -> DocumentCollectionAccess:
    return DocumentCollectionAccess(
        session=session,
        collection_repo=CollectionRepository.from_session(session),
        shared_workspace_repo=SharedWorkspaceRepository.from_session(session),
    )


def get_document_collection_access(
    session: AsyncSession = Depends(get_db_session),
) -> DocumentCollectionAccess:
    return build_document_collection_access(session)


def get_search_query_repository(
    session: AsyncSession = Depends(get_db_session),
) -> SearchQueryRepository:
    return SearchQueryRepository.from_session(session)


def get_document_service(
    session: AsyncSession = Depends(get_db_session),
    embedding_provider: EmbeddingProvider = Depends(get_embedding_provider),
    file_storage: FileStorage = Depends(build_file_storage),
    processing_service: DocumentProcessingService = Depends(get_document_processing_service),
) -> DocumentService:
    return DocumentService.from_session(
        session,
        embedding_provider=embedding_provider,
        file_storage=file_storage,
        processing_service=processing_service,
    )


__all__ = [
    "build_document_collection_access",
    "get_cache",
    "get_chunk_repository",
    "get_document_activity_repository",
    "get_document_collection_access",
    "get_document_processing_service",
    "get_document_repository",
    "get_document_service",
    "get_document_status_cache",
    "get_embedding_provider",
    "get_redis",
    "get_search_query_repository",
    "get_shared_workspace_repository",
    "get_task_dispatcher",
]
