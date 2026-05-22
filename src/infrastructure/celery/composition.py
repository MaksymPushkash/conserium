from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from src.application.dtos.repo_sync_dtos import RepoSyncDTO, RunRepoSyncDTO
from src.application.services.enrichment.enrichment_service import EnrichmentService
from src.application.use_cases.documents.enrich_document_use_case import EnrichDocumentUseCase
from src.application.use_cases.documents.process_document_embeddings_use_case import (
    ProcessDocumentEmbeddingsUseCase,
)
from src.application.use_cases.documents.process_document_ingestion_use_case import (
    ProcessDocumentIngestionUseCase,
)
from src.application.use_cases.documents.process_image_document_use_case import ProcessImageDocumentUseCase
from src.application.use_cases.repo_syncs import DrainRepoSyncOutboxUseCase, RunRepoSyncUseCase
from src.core.config import settings
from src.infrastructure.ai.extractors.image_extractor import ImageExtractor
from src.infrastructure.ai.extractors.pdf_extractor import PdfExtractor
from src.infrastructure.ai.extractors.url_extractor import UrlExtractor
from src.infrastructure.ai.extractors.youtube_extractor import YoutubeExtractor
from src.infrastructure.ai.providers.cached_embedding_provider import CachedEmbeddingProvider
from src.infrastructure.ai.providers.hf_classifier_provider import HFClassifierProvider
from src.infrastructure.ai.providers.hf_ner_provider import HFNERProvider
from src.infrastructure.ai.providers.openai_document_summary_service import OpenAIDocumentSummaryService
from src.infrastructure.ai.providers.openai_embedding_provider import OpenAIEmbeddingProvider
from src.infrastructure.cache.document_status_cache import RedisDocumentStatusCache
from src.infrastructure.cache.redis_cache import RedisCache
from src.infrastructure.celery.dependencies import get_worker_redis, get_worker_session_factory
from src.infrastructure.celery.dispatcher import CeleryTaskDispatcher
from src.infrastructure.database.services.document_tag_sync import SQLAlchemyDocumentTagSync
from src.infrastructure.database.services.document_topic_sync import SQLAlchemyDocumentTopicSync
from src.infrastructure.database.unit_of_work import SQLAlchemyUnitOfWork
from src.infrastructure.integrations.github_repository_client import GitHubRepositoryClient
from src.infrastructure.storage.factory import build_file_storage
from src.infrastructure.text_processing.simple_text_chunker import SimpleTextChunker

logger = logging.getLogger(__name__)


async def process_document_ingestion(document_id: str) -> dict[str, str]:
    factory = get_worker_session_factory()
    redis = get_worker_redis(decode_responses=True)

    try:
        async with factory() as session:
            use_case = ProcessDocumentIngestionUseCase(
                uow=SQLAlchemyUnitOfWork(session),
                status_cache=RedisDocumentStatusCache(redis),
                task_dispatcher=CeleryTaskDispatcher(),
                text_chunker=SimpleTextChunker(),
                file_storage=build_file_storage(),
                url_extractor=UrlExtractor(),
                youtube_extractor=YoutubeExtractor(),
                pdf_extractor=PdfExtractor(),
            )
            result = await use_case(document_id)
            return {"document_id": result.document_id, "status": result.status}
    finally:
        await redis.aclose()


async def process_document_embeddings(
    *,
    document_id: str,
    raw_text: str,
    chunks_data: list[dict[str, Any]],
    expected_content_hash: str | None = None,
) -> dict[str, str]:
    factory = get_worker_session_factory()
    redis = get_worker_redis(decode_responses=False)
    embedding_provider = CachedEmbeddingProvider(
        OpenAIEmbeddingProvider(),
        RedisCache(redis),
    )

    try:
        async with factory() as session:
            use_case = ProcessDocumentEmbeddingsUseCase(
                uow=SQLAlchemyUnitOfWork(session),
                status_cache=RedisDocumentStatusCache(redis),
                embedding_provider=embedding_provider,
            )
            result = await use_case(
                document_id=document_id,
                raw_text=raw_text,
                chunks_data=chunks_data,
                expected_content_hash=expected_content_hash,
            )
            return {"document_id": result.document_id, "status": result.status}
    finally:
        await embedding_provider.aclose()
        await redis.aclose()


async def enrich_document(document_id: str) -> dict[str, object]:
    factory = get_worker_session_factory()
    redis = get_worker_redis(decode_responses=False)
    embedding_provider = CachedEmbeddingProvider(OpenAIEmbeddingProvider(), RedisCache(redis))

    try:
        async with factory() as session:
            enrichment_service = EnrichmentService(
                uow=SQLAlchemyUnitOfWork(session),
                embedding_provider=embedding_provider,
                ner_provider=HFNERProvider(),
                classifier_provider=HFClassifierProvider(),
                tag_sync=SQLAlchemyDocumentTagSync(session),
                topic_sync=SQLAlchemyDocumentTopicSync(session),
                summary_service=OpenAIDocumentSummaryService(),
            )
            use_case = EnrichDocumentUseCase(enrichment_service)
            result = await use_case.execute(UUID(document_id))
        status_cache = RedisDocumentStatusCache(redis)
        await status_cache.set_status(
            UUID(document_id),
            status="READY",
            progress=100,
            message="Processing complete.",
        )
        return result
    finally:
        await embedding_provider.aclose()
        await redis.aclose()


async def process_image_document(document_id: str) -> dict[str, str]:
    factory = get_worker_session_factory()
    redis = get_worker_redis(decode_responses=True)

    try:
        async with factory() as session:
            use_case = ProcessImageDocumentUseCase(
                uow=SQLAlchemyUnitOfWork(session),
                status_cache=RedisDocumentStatusCache(redis),
                task_dispatcher=CeleryTaskDispatcher(),
                text_chunker=SimpleTextChunker(),
                file_storage=build_file_storage(),
                image_extractor=ImageExtractor(),
            )
            result = await use_case(document_id)
            return {"document_id": result.document_id, "status": result.status}
    finally:
        await redis.aclose()


async def run_due_repo_syncs() -> dict[str, int]:
    factory = get_worker_session_factory()
    redis = get_worker_redis(decode_responses=True)
    try:
        async with factory() as session:
            uow = SQLAlchemyUnitOfWork(session)
            cutoff = datetime.now(UTC) - timedelta(minutes=settings.REPO_SYNC_INTERVAL_MINUTES)
            repo_syncs = await _list_due_repo_syncs(uow, cutoff=cutoff)
            use_case = RunRepoSyncUseCase(
                uow=uow,
                github_client=GitHubRepositoryClient(),
                task_dispatcher=CeleryTaskDispatcher(),
            )
            completed = 0
            failed = 0
            for repo_sync in repo_syncs:
                try:
                    await use_case(
                        RunRepoSyncDTO(
                            user_id=repo_sync.user_id,
                            repo_sync_id=repo_sync.id,
                            max_files=50,
                        )
                    )
                    completed += 1
                except Exception as exc:
                    logger.exception("Repo sync failed for %s/%s@%s: %s", repo_sync.owner, repo_sync.repo, repo_sync.branch, exc)
                    failed += 1
            return {"queued": len(repo_syncs), "completed": completed, "failed": failed}
    finally:
        await redis.aclose()


async def drain_repo_sync_outbox(*, limit: int = 100) -> dict[str, int]:
    factory = get_worker_session_factory()
    redis = get_worker_redis(decode_responses=True)
    try:
        async with factory() as session:
            use_case = DrainRepoSyncOutboxUseCase(
                uow=SQLAlchemyUnitOfWork(session),
                status_cache=RedisDocumentStatusCache(redis),
                task_dispatcher=CeleryTaskDispatcher(),
            )
            result = await use_case(limit=limit)
            return {
                "claimed": result.claimed,
                "dispatched": result.dispatched,
                "failed": result.failed,
                "permanently_failed": result.permanently_failed,
            }
    finally:
        await redis.aclose()


async def _list_due_repo_syncs(uow: SQLAlchemyUnitOfWork, *, cutoff: datetime) -> list[RepoSyncDTO]:
    async with uow:
        return await uow.repo_sync_repo.list_due_for_sync(
            before=cutoff,
            limit=settings.REPO_SYNC_BATCH_LIMIT,
        )
