from __future__ import annotations

from aio_pika.abc import ExchangeType
from taskiq import TaskiqEvents, TaskiqScheduler, TaskiqState
from taskiq.middlewares import SmartRetryMiddleware
from taskiq.schedule_sources import LabelScheduleSource
from taskiq_aio_pika import AioPikaBroker, Exchange, Queue, QueueType
from taskiq_redis import RedisAsyncResultBackend

from src.settings import settings
from src.startup_checks import validate_startup_settings
from src.worker.dependencies import dispose_worker_engine
from src.worker.error_handling import RetryableTaskError

QUEUE_NAMES = (
    "document_processing",
    "embeddings",
    "notifications",
    "cleanup",
    "media_processing",
    "hf_processing",
)

TASK_QUEUES = tuple(
    Queue(
        name=queue_name,
        type=QueueType.CLASSIC,
        durable=True,
        max_priority=10,
        routing_key=queue_name,
    )
    for queue_name in QUEUE_NAMES
)

TASK_SCHEDULES = {
    "run-due-repo-syncs": {
        "task": "src.repo_syncs.tasks.run_due_repo_syncs_task",
        "interval": 900.0,
        "queue_name": "cleanup",
    },
    "drain-repo-sync-outbox": {
        "task": "src.repo_syncs.tasks.drain_repo_sync_outbox_task",
        "interval": 60.0,
        "queue_name": "cleanup",
    },
    "drain-document-processing-outbox": {
        "task": "src.documents.tasks.drain_document_processing_outbox_task",
        "interval": 60.0,
        "queue_name": "cleanup",
    },
}

if settings.PROACTIVE_NOTIFICATIONS_ENABLED:
    TASK_SCHEDULES.update(
        {
            "deliver-daily-digest-notifications": {
                "task": "src.notifications.tasks.deliver_daily_digest_notifications_task",
                "interval": 86400.0,
                "queue_name": "notifications",
            },
            "deliver-weekly-report-notifications": {
                "task": "src.notifications.tasks.deliver_weekly_report_notifications_task",
                "interval": 604800.0,
                "queue_name": "notifications",
            },
            "deliver-learning-goal-reminder-notifications": {
                "task": "src.notifications.tasks.deliver_learning_goal_reminder_notifications_task",
                "interval": 21600.0,
                "queue_name": "notifications",
            },
        }
    )


taskiq_broker = AioPikaBroker(
    settings.TASKIQ_BROKER_URL,
    exchange=Exchange(
        name="conserium",
        type=ExchangeType.DIRECT,
        durable=True,
    ),
    task_queues=list(TASK_QUEUES),
    delay_queue=Queue(
        name="conserium.delay",
        type=QueueType.CLASSIC,
        durable=True,
        routing_key="conserium.delay",
    ),
    qos=1,
).with_result_backend(
    RedisAsyncResultBackend(
        settings.TASKIQ_RESULT_BACKEND_URL,
        result_ex_time=3600,
    )
).with_middlewares(
    SmartRetryMiddleware(
        default_retry_count=3,
        default_delay=60,
        use_delay_exponent=True,
        max_delay_exponent=3600,
        types_of_exceptions=(RetryableTaskError,),
    )
)

scheduler = TaskiqScheduler(
    broker=taskiq_broker,
    sources=[LabelScheduleSource(taskiq_broker)],
)


@taskiq_broker.on_event(TaskiqEvents.WORKER_STARTUP)
async def validate_worker_startup(state: TaskiqState) -> None:
    _ = state
    validate_startup_settings()


@taskiq_broker.on_event(TaskiqEvents.WORKER_SHUTDOWN)
async def shutdown_worker_runtime(state: TaskiqState) -> None:
    _ = state
    await dispose_worker_engine()


async def startup_taskiq_client() -> None:
    await taskiq_broker.startup()


async def shutdown_taskiq_client() -> None:
    await taskiq_broker.shutdown()


async def declare_configured_queues() -> None:
    await startup_taskiq_client()


def _queue_by_name(queue_name: str) -> Queue:
    for queue in TASK_QUEUES:
        if queue.name == queue_name:
            return queue
    raise RuntimeError(f"Unknown Taskiq queue: {queue_name}")


def get_default_broker() -> AioPikaBroker:
    return taskiq_broker.with_queues(
        _queue_by_name("document_processing"),
        _queue_by_name("notifications"),
        _queue_by_name("cleanup"),
    )


def get_embeddings_broker() -> AioPikaBroker:
    return taskiq_broker.with_queues(_queue_by_name("embeddings"))


def get_media_broker() -> AioPikaBroker:
    return taskiq_broker.with_queues(
        _queue_by_name("media_processing"),
        _queue_by_name("hf_processing"),
    )
