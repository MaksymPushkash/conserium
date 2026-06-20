from celery import Celery
from celery.signals import worker_init, worker_process_init, worker_process_shutdown
from kombu import Exchange, Queue

from src.settings import settings
from src.startup_checks import validate_startup_settings
from src.worker.dependencies import initialize_worker_runtime, shutdown_worker_runtime
from src.worker.registry import TASK_MODULES
from src.worker.task_names import (
    DOCUMENT_EMBED_AND_FINALIZE_TASK,
    DOCUMENT_ENRICH_TASK,
    DOCUMENT_PROCESS_IMAGE_TASK,
    DOCUMENT_PROCESS_TASK,
    DOCUMENT_PROCESSING_OUTBOX_DRAIN_TASK,
    NOTIFICATION_DAILY_DIGEST_TASK,
    NOTIFICATION_LEARNING_GOAL_REMINDER_TASK,
    NOTIFICATION_WEEKLY_REPORT_TASK,
    REPO_SYNC_OUTBOX_DRAIN_TASK,
    REPO_SYNC_RUN_DUE_TASK,
)

_conserium_exchange = Exchange("conserium", type="direct", durable=True)


_QUEUES = (
    Queue("document_processing", _conserium_exchange, routing_key="document_processing", durable=True),
    Queue("embeddings", _conserium_exchange, routing_key="embeddings", durable=True),
    Queue("notifications", _conserium_exchange, routing_key="notifications", durable=True),
    Queue("cleanup", _conserium_exchange, routing_key="cleanup", durable=True),
    Queue("media_processing", _conserium_exchange, routing_key="media_processing", durable=True),
    Queue("hf_processing", _conserium_exchange, routing_key="hf_processing", durable=True),
)


_beat_schedule = {
    "run-due-repo-syncs": {
        "task": REPO_SYNC_RUN_DUE_TASK,
        "schedule": 900.0,
    },
    "drain-repo-sync-outbox": {
        "task": REPO_SYNC_OUTBOX_DRAIN_TASK,
        "schedule": 60.0,
    },
    "drain-document-processing-outbox": {
        "task": DOCUMENT_PROCESSING_OUTBOX_DRAIN_TASK,
        "schedule": 60.0,
    },
}

if settings.PROACTIVE_NOTIFICATIONS_ENABLED:
    _beat_schedule.update(
        {
            "deliver-daily-digest-notifications": {
                "task": NOTIFICATION_DAILY_DIGEST_TASK,
                "schedule": 86400.0,
            },
            "deliver-weekly-report-notifications": {
                "task": NOTIFICATION_WEEKLY_REPORT_TASK,
                "schedule": 604800.0,
            },
            "deliver-learning-goal-reminder-notifications": {
                "task": NOTIFICATION_LEARNING_GOAL_REMINDER_TASK,
                "schedule": 21600.0,
            },
        }
    )


celery_app = Celery(
    "conserium",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=list(TASK_MODULES),
)

celery_app.conf.update(
    task_queues=_QUEUES,
    task_default_queue="document_processing",
    task_default_exchange="conserium",
    task_default_routing_key="document_processing",
    task_routes={
        DOCUMENT_PROCESS_TASK: {"queue": "document_processing"},
        DOCUMENT_EMBED_AND_FINALIZE_TASK: {"queue": "embeddings"},
        DOCUMENT_PROCESS_IMAGE_TASK: {"queue": "media_processing"},
        DOCUMENT_ENRICH_TASK: {"queue": "media_processing"},
        REPO_SYNC_RUN_DUE_TASK: {"queue": "cleanup"},
        REPO_SYNC_OUTBOX_DRAIN_TASK: {"queue": "cleanup"},
        DOCUMENT_PROCESSING_OUTBOX_DRAIN_TASK: {"queue": "cleanup"},
        NOTIFICATION_DAILY_DIGEST_TASK: {"queue": "notifications"},
        NOTIFICATION_WEEKLY_REPORT_TASK: {"queue": "notifications"},
        NOTIFICATION_LEARNING_GOAL_REMINDER_TASK: {"queue": "notifications"},
    },
    beat_schedule=_beat_schedule,


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
worker_process_init.connect(initialize_worker_runtime)
worker_process_shutdown.connect(shutdown_worker_runtime)
