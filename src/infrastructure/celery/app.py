"""Celery application instance and queue configuration.

This module is the single authoritative source of the Celery app object.
Import it as:

    from src.infrastructure.celery.app import celery_app

Workers are started with:
    celery -A src.infrastructure.celery worker --queues document_processing ...
"""

from celery import Celery
from kombu import Exchange, Queue

from src.core.config import settings

_cortex_exchange = Exchange("cortex", type="direct", durable=True)


# Queues
# 1. document_processing  — heavy I/O: extract text from PDF/URL, chunk text
#                           Concurrency: 4 (CPU-bound light + network-bound)
# 2. embeddings           — OpenAI API calls + Redis caching
#                           Concurrency: 8 (mostly waiting on network)
# 3. notifications        — future: email / webhook delivery
#                           Concurrency: 4
# 4. cleanup              — soft-delete sweeps, orphan file removal
#                           Concurrency: 2
# 5. hf_processing        — CPU-heavy HuggingFace models
#                           Concurrency: 2, separate image
_QUEUES = (
    Queue("document_processing", _cortex_exchange, routing_key="document_processing", durable=True),
    Queue("embeddings", _cortex_exchange, routing_key="embeddings", durable=True),
    Queue("notifications", _cortex_exchange, routing_key="notifications", durable=True),
    Queue("cleanup", _cortex_exchange, routing_key="cleanup", durable=True),
    Queue("hf_processing", _cortex_exchange, routing_key="hf_processing", durable=True),
)


celery_app = Celery(
    "cortex",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=[
        "src.infrastructure.celery.tasks.document_processing",
        "src.infrastructure.celery.tasks.embeddings",
    ],
)

celery_app.conf.update(
    task_queues=_QUEUES,
    task_default_queue="document_processing",
    task_default_exchange="cortex",
    task_default_routing_key="document_processing",
    task_routes={
        "src.infrastructure.celery.tasks.document_processing.*": {
            "queue": "document_processing",
        },
        "src.infrastructure.celery.tasks.embeddings.*": {
            "queue": "embeddings",
        },
        "src.infrastructure.celery.tasks.hf_processing.*": {
            "queue": "hf_processing",
        },
    },


    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    result_expires=3600,


    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,


    timezone="UTC",
    enable_utc=True,

    
    task_max_retries=3,
    task_default_retry_delay=60,


    worker_send_task_events=True,
    task_send_sent_event=True,
)
