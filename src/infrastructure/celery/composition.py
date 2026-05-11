from __future__ import annotations

from typing import Any
from uuid import UUID

from src.application.services.enrichment.enrichment_service import EnrichmentService
from src.application.use_cases.documents.enrich_document_use_case import EnrichDocumentUseCase
from src.application.use_cases.documents.process_document_embeddings_use_case import (
    ProcessDocumentEmbeddingsUseCase,
)
from src.application.use_cases.documents.process_document_ingestion_use_case import (
    ProcessDocumentIngestionUseCase,
)
from src.application.use_cases.documents.process_image_document_use_case import ProcessImageDocumentUseCase
from src.infrastructure.ai.extractors.image_extractor import ImageExtractor
from src.infrastructure.ai.extractors.pdf_extractor import PdfExtractor
from src.infrastructure.ai.extractors.url_extractor import UrlExtractor
from src.infrastructure.ai.extractors.youtube_extractor import YoutubeExtractor
from src.infrastructure.ai.providers.cached_embedding_provider import CachedEmbeddingProvider
from src.infrastructure.ai.providers.hf_classifier_provider import HFClassifierProvider
from src.infrastructure.ai.providers.hf_ner_provider import HFNERProvider
from src.infrastructure.ai.providers.openai_embedding_provider import OpenAIEmbeddingProvider
from src.infrastructure.cache.document_status_cache import RedisDocumentStatusCache
from src.infrastructure.cache.redis_cache import RedisCache
from src.infrastructure.celery.dependencies import get_worker_redis, get_worker_session_factory
from src.infrastructure.celery.dispatcher import CeleryTaskDispatcher
from src.infrastructure.database.services.document_tag_sync import SQLAlchemyDocumentTagSync
from src.infrastructure.database.unit_of_work import SQLAlchemyUnitOfWork
from src.infrastructure.storage.factory import build_file_storage
from src.infrastructure.text_processing.simple_text_chunker import SimpleTextChunker


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
        status_cache = RedisDocumentStatusCache(redis)
        await status_cache.set_status(
            UUID(document_id),
            status="PROCESSING",
            progress=95,
            message="Enriching metadata...",
        )
        async with factory() as session:
            enrichment_service = EnrichmentService(
                uow=SQLAlchemyUnitOfWork(session),
                embedding_provider=embedding_provider,
                ner_provider=HFNERProvider(),
                classifier_provider=HFClassifierProvider(),
                tag_sync=SQLAlchemyDocumentTagSync(session),
            )
            use_case = EnrichDocumentUseCase(enrichment_service)
            result = await use_case.execute(UUID(document_id))
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
