import logging
import uuid
from typing import Any

from celery import shared_task

from src.application.services.enrichment.enrichment_service import EnrichmentService
from src.application.use_cases.documents.enrich_document_use_case import EnrichDocumentUseCase
from src.infrastructure.ai.providers.cached_embedding_provider import CachedEmbeddingProvider
from src.infrastructure.ai.providers.hf_classifier_provider import HFClassifierProvider
from src.infrastructure.ai.providers.hf_ner_provider import HFNERProvider
from src.infrastructure.ai.providers.openai_embedding_provider import OpenAIEmbeddingProvider
from src.infrastructure.cache.redis_cache import RedisCache
from src.infrastructure.celery.dependencies import get_worker_redis, get_worker_session_factory
from src.infrastructure.database.services.document_tag_sync import SQLAlchemyDocumentTagSync
from src.infrastructure.database.unit_of_work import SQLAlchemyUnitOfWork

logger = logging.getLogger(__name__)


@shared_task(queue="hf_processing", bind=True)  # type: ignore[untyped-decorator]
def enrich_document_task(self: Any, document_id: str) -> dict[str, object]:
    try:
        import asyncio

        return asyncio.run(_run_enrich_document_use_case(document_id))
    except Exception as e:
        logger.exception("Document enrichment failed for doc %s: %s", document_id, e)
        return {
            "status": "failed",
            "document_id": document_id,
            "error": str(e),
        }


async def _run_enrich_document_use_case(document_id: str) -> dict[str, object]:
    factory = get_worker_session_factory()
    redis = get_worker_redis(decode_responses=False)

    async with factory() as session:
        enrichment_service = EnrichmentService(
            uow=SQLAlchemyUnitOfWork(session),
            embedding_provider=CachedEmbeddingProvider(OpenAIEmbeddingProvider(), RedisCache(redis)),
            ner_provider=HFNERProvider(),
            classifier_provider=HFClassifierProvider(),
            tag_sync=SQLAlchemyDocumentTagSync(session),
        )
        use_case = EnrichDocumentUseCase(enrichment_service)
        result = await use_case.execute(uuid.UUID(document_id))
        return result
