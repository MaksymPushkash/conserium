from celery import Celery
from celery.signals import worker_init
from kombu import Exchange, Queue

from src.core.config import settings
from src.core.startup_checks import validate_startup_settings

_cortex_exchange = Exchange("cortex", type="direct", durable=True)


_QUEUES = (
    Queue("document_processing", _cortex_exchange, routing_key="document_processing", durable=True),
    Queue("embeddings", _cortex_exchange, routing_key="embeddings", durable=True),
    Queue("notifications", _cortex_exchange, routing_key="notifications", durable=True),
    Queue("cleanup", _cortex_exchange, routing_key="cleanup", durable=True),
    Queue("media_processing", _cortex_exchange, routing_key="media_processing", durable=True),
    Queue("hf_processing", _cortex_exchange, routing_key="hf_processing", durable=True),
)


celery_app = Celery(
    "cortex",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=[
        "src.infrastructure.celery.tasks.document_ingestion_task",
        "src.infrastructure.celery.tasks.embedding_tasks",
        "src.infrastructure.celery.tasks.enrichment_tasks",
        "src.infrastructure.celery.tasks.media_processing_tasks",
        "src.infrastructure.celery.tasks.repo_sync_tasks",
    ],
)

celery_app.conf.update(
    task_queues=_QUEUES,
    task_default_queue="document_processing",
    task_default_exchange="cortex",
    task_default_routing_key="document_processing",
    task_routes={
        "src.infrastructure.celery.tasks.document_ingestion_task.*": {
            "queue": "document_processing",
        },
        "src.infrastructure.celery.tasks.embedding_tasks.*": {
            "queue": "embeddings",
        },
        "src.infrastructure.celery.tasks.media_processing_tasks.*": {
            "queue": "media_processing",
        },
        "src.infrastructure.celery.tasks.enrichment_tasks.*": {
            "queue": "media_processing",
        },
        "src.infrastructure.celery.tasks.repo_sync_tasks.*": {
            "queue": "cleanup",
        },
    },
    beat_schedule={
        "run-due-repo-syncs": {
            "task": "src.infrastructure.celery.tasks.repo_sync_tasks.run_due_repo_syncs_task",
            "schedule": 900.0,
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


def declare_configured_queues() -> None:
    with celery_app.connection_or_acquire() as connection:
        channel = connection.channel()
        try:
            for queue_def in celery_app.conf.task_queues:
                queue_def(channel).declare()
        finally:
            channel.close()


def _validate_worker_startup(**_: object) -> None:
    validate_startup_settings()


worker_init.connect(_validate_worker_startup)
