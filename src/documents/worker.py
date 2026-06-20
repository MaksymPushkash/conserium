from __future__ import annotations

from typing import Any
from uuid import UUID

from src.documents.chunk_repository import ChunkRepository
from src.documents.document_repository import DocumentRepository
from src.documents.processing import (
    DocumentEmbeddingProcessor,
    DocumentEnricher,
    DocumentIngestionProcessor,
    DocumentProcessingService,
    ImageDocumentProcessor,
)
from src.documents.processing_outbox_repository import DocumentProcessingOutboxRepository
from src.documents.services.enrichment.enrichment_service import EnrichmentService
from src.documents.status_cache import RedisDocumentStatusCache
from src.documents.tag_sync import DocumentTagSync
from src.documents.text_chunker import SimpleTextChunker
from src.documents.topic_sync import DocumentTopicSync
from src.kit.ai.extractors.image_extractor import ImageExtractor
from src.kit.ai.extractors.pdf_extractor import PdfExtractor
from src.kit.ai.extractors.url_extractor import UrlExtractor
from src.kit.ai.extractors.youtube_extractor import YoutubeExtractor
from src.kit.ai.providers.cached_embedding_provider import CachedEmbeddingProvider
from src.kit.ai.providers.hf_classifier_provider import HFClassifierProvider
from src.kit.ai.providers.hf_ner_provider import HFNERProvider
from src.kit.ai.providers.openai_document_summary_service import OpenAIDocumentSummaryService
from src.kit.ai.providers.openai_embedding_provider import OpenAIEmbeddingProvider
from src.kit.cache.redis_cache import RedisCache
from src.kit.storage.factory import build_file_storage
from src.worker.dependencies import get_worker_redis, get_worker_session_factory
from src.worker.dispatcher import CeleryTaskDispatcher


async def acknowledge_document_processing_task_start(*, task_id: str | None, document_id: str) -> bool:
    document_uuid = UUID(document_id)
    factory = get_worker_session_factory()
    redis = get_worker_redis(decode_responses=True)
    async with factory() as session:
        try:
            service = DocumentProcessingService(
                session,
                DocumentRepository.from_session(session),
                DocumentProcessingOutboxRepository.from_session(session),
                RedisDocumentStatusCache(redis),
                CeleryTaskDispatcher(),
            )
            return await service.acknowledge(task_id=task_id, document_id=document_uuid)
        finally:
            await redis.aclose()


async def acknowledge_and_process_document_ingestion(*, task_id: str | None, document_id: str) -> dict[str, str]:
    should_process = await acknowledge_document_processing_task_start(task_id=task_id, document_id=document_id)
    if not should_process:
        return {"document_id": document_id, "status": "SKIPPED"}
    return await process_document_ingestion(document_id)


async def process_document_ingestion(document_id: str) -> dict[str, str]:
    factory = get_worker_session_factory()
    redis = get_worker_redis(decode_responses=True)

    try:
        async with factory() as session:
            handler = DocumentIngestionProcessor(
                session=session,
                document_repo=DocumentRepository.from_session(session),
                status_cache=RedisDocumentStatusCache(redis),
                task_dispatcher=CeleryTaskDispatcher(),
                text_chunker=SimpleTextChunker(),
                file_storage=build_file_storage(),
                url_extractor=UrlExtractor(),
                youtube_extractor=YoutubeExtractor(),
                pdf_extractor=PdfExtractor(),
            )
            result = await handler(document_id)
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
            handler = DocumentEmbeddingProcessor(
                session=session,
                document_repo=DocumentRepository.from_session(session),
                status_cache=RedisDocumentStatusCache(redis),
                embedding_provider=embedding_provider,
                chunk_repo=ChunkRepository.from_session(session),
            )
            result = await handler(
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
                session=session,
                document_repo=DocumentRepository.from_session(session),
                embedding_provider=embedding_provider,
                chunk_repo=ChunkRepository.from_session(session),
                ner_provider=HFNERProvider(),
                classifier_provider=HFClassifierProvider(),
                tag_sync=DocumentTagSync(session),
                topic_sync=DocumentTopicSync(session),
                summary_service=OpenAIDocumentSummaryService(),
            )
            handler = DocumentEnricher(enrichment_service)
            result = await handler.execute(UUID(document_id))
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
            handler = ImageDocumentProcessor(
                session=session,
                document_repo=DocumentRepository.from_session(session),
                status_cache=RedisDocumentStatusCache(redis),
                task_dispatcher=CeleryTaskDispatcher(),
                text_chunker=SimpleTextChunker(),
                file_storage=build_file_storage(),
                image_extractor=ImageExtractor(),
            )
            result = await handler(document_id)
            return {"document_id": result.document_id, "status": result.status}
    finally:
        await redis.aclose()


async def drain_document_processing_outbox(*, limit: int = 100) -> dict[str, int]:
    factory = get_worker_session_factory()
    redis = get_worker_redis(decode_responses=True)
    try:
        async with factory() as session:
            service = DocumentProcessingService(
                session,
                DocumentRepository.from_session(session),
                DocumentProcessingOutboxRepository.from_session(session),
                RedisDocumentStatusCache(redis),
                CeleryTaskDispatcher(),
            )
            result = await service.drain(limit=limit)
            return {
                "claimed": result.claimed,
                "dispatched": result.dispatched,
                "failed": result.failed,
                "permanently_failed": result.permanently_failed,
            }
    finally:
        await redis.aclose()
