from __future__ import annotations

import asyncio
from typing import Any

import structlog

from src.application.use_cases.documents.process_audio_document_use_case import (
    ProcessAudioDocumentUseCase,
)
from src.application.use_cases.documents.process_image_document_use_case import (
    ProcessImageDocumentUseCase,
)
from src.infrastructure.ai.extractors.audio_extractor import AudioExtractor
from src.infrastructure.ai.extractors.image_extractor import ImageExtractor
from src.infrastructure.cache.document_status_cache import RedisDocumentStatusCache
from src.infrastructure.celery.app import celery_app
from src.infrastructure.celery.dependencies import get_worker_redis, get_worker_session_factory
from src.infrastructure.celery.dispatcher import CeleryTaskDispatcher
from src.infrastructure.celery.tasks.document_processing import _handle_failure
from src.infrastructure.database.unit_of_work import SQLAlchemyUnitOfWork
from src.infrastructure.storage.factory import build_file_storage
from src.infrastructure.text_processing.simple_text_chunker import SimpleTextChunker

logger = structlog.get_logger(__name__)


@celery_app.task(  # type: ignore[untyped-decorator]
    name="src.infrastructure.celery.tasks.hf_processing.process_audio_document",
    queue="hf_processing",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    acks_late=True,
)
def process_audio_document(self: Any, document_id: str) -> dict[str, str]:
    log = logger.bind(document_id=document_id, task_id=self.request.id)
    log.info("HF audio processing task started")

    try:
        result = asyncio.run(_run_process_audio_document_use_case(document_id=document_id))
        log.info("HF audio processing task completed", status=result["status"])
        return result
    except Exception as exc:
        log.exception("HF audio processing task failed", error=str(exc))
        if self.request.retries >= self.max_retries:
            _handle_failure(document_id, str(exc), log)
            return {"document_id": document_id, "status": "FAILED"}
        raise self.retry(exc=exc) from exc


@celery_app.task(  # type: ignore[untyped-decorator]
    name="src.infrastructure.celery.tasks.hf_processing.process_image_document",
    queue="hf_processing",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    acks_late=True,
)
def process_image_document(self: Any, document_id: str) -> dict[str, str]:
    log = logger.bind(document_id=document_id, task_id=self.request.id)
    log.info("HF image processing task started")

    try:
        result = asyncio.run(_run_process_image_document_use_case(document_id=document_id))
        log.info("HF image processing task completed", status=result["status"])
        return result
    except Exception as exc:
        log.exception("HF image processing task failed", error=str(exc))
        if self.request.retries >= self.max_retries:
            _handle_failure(document_id, str(exc), log)
            return {"document_id": document_id, "status": "FAILED"}
        raise self.retry(exc=exc) from exc


async def _run_process_audio_document_use_case(*, document_id: str) -> dict[str, str]:
    factory = get_worker_session_factory()
    redis = get_worker_redis(decode_responses=True)

    async with factory() as session:
        use_case = ProcessAudioDocumentUseCase(
            uow=SQLAlchemyUnitOfWork(session),
            status_cache=RedisDocumentStatusCache(redis),
            task_dispatcher=CeleryTaskDispatcher(),
            text_chunker=SimpleTextChunker(),
            file_storage=build_file_storage(),
            audio_extractor=AudioExtractor(),
        )
        result = await use_case(document_id)
        return {"document_id": result.document_id, "status": result.status}


async def _run_process_image_document_use_case(*, document_id: str) -> dict[str, str]:
    factory = get_worker_session_factory()
    redis = get_worker_redis(decode_responses=True)

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
