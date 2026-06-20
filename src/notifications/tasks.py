from src.worker.app import celery_app
from src.worker.dependencies import run_worker_async
from src.worker.task_names import (
    NOTIFICATION_DAILY_DIGEST_TASK,
    NOTIFICATION_LEARNING_GOAL_REMINDER_TASK,
    NOTIFICATION_WEEKLY_REPORT_TASK,
)


@celery_app.task(  # type: ignore[untyped-decorator]
    name=NOTIFICATION_DAILY_DIGEST_TASK
)
def deliver_daily_digest_notifications_task() -> dict[str, int]:
    from src.notifications.worker import deliver_daily_digest_notifications

    return run_worker_async(deliver_daily_digest_notifications())


@celery_app.task(  # type: ignore[untyped-decorator]
    name=NOTIFICATION_WEEKLY_REPORT_TASK
)
def deliver_weekly_report_notifications_task() -> dict[str, int]:
    from src.notifications.worker import deliver_weekly_report_notifications

    return run_worker_async(deliver_weekly_report_notifications())


@celery_app.task(  # type: ignore[untyped-decorator]
    name=NOTIFICATION_LEARNING_GOAL_REMINDER_TASK
)
def deliver_learning_goal_reminder_notifications_task() -> dict[str, int]:
    from src.notifications.worker import deliver_learning_goal_reminder_notifications

    return run_worker_async(deliver_learning_goal_reminder_notifications())


__all__ = [
    "deliver_daily_digest_notifications_task",
    "deliver_learning_goal_reminder_notifications_task",
    "deliver_weekly_report_notifications_task",
]
