from src.settings import settings
from src.worker.app import taskiq_broker
from src.worker.task_names import (
    NOTIFICATION_DAILY_DIGEST_TASK,
    NOTIFICATION_LEARNING_GOAL_REMINDER_TASK,
    NOTIFICATION_WEEKLY_REPORT_TASK,
)

_DAILY_DIGEST_SCHEDULE = (
    [
        {
            "schedule_id": "deliver-daily-digest-notifications",
            "interval": 86400.0,
            "labels": {"queue_name": "notifications"},
        }
    ]
    if settings.PROACTIVE_NOTIFICATIONS_ENABLED
    else []
)
_WEEKLY_REPORT_SCHEDULE = (
    [
        {
            "schedule_id": "deliver-weekly-report-notifications",
            "interval": 604800.0,
            "labels": {"queue_name": "notifications"},
        }
    ]
    if settings.PROACTIVE_NOTIFICATIONS_ENABLED
    else []
)
_LEARNING_GOAL_SCHEDULE = (
    [
        {
            "schedule_id": "deliver-learning-goal-reminder-notifications",
            "interval": 21600.0,
            "labels": {"queue_name": "notifications"},
        }
    ]
    if settings.PROACTIVE_NOTIFICATIONS_ENABLED
    else []
)


@taskiq_broker.task(
    task_name=NOTIFICATION_DAILY_DIGEST_TASK,
    queue_name="notifications",
    schedule=_DAILY_DIGEST_SCHEDULE,
)
async def deliver_daily_digest_notifications_task() -> dict[str, int]:
    from src.notifications.worker import deliver_daily_digest_notifications

    return await deliver_daily_digest_notifications()


@taskiq_broker.task(
    task_name=NOTIFICATION_WEEKLY_REPORT_TASK,
    queue_name="notifications",
    schedule=_WEEKLY_REPORT_SCHEDULE,
)
async def deliver_weekly_report_notifications_task() -> dict[str, int]:
    from src.notifications.worker import deliver_weekly_report_notifications

    return await deliver_weekly_report_notifications()


@taskiq_broker.task(
    task_name=NOTIFICATION_LEARNING_GOAL_REMINDER_TASK,
    queue_name="notifications",
    schedule=_LEARNING_GOAL_SCHEDULE,
)
async def deliver_learning_goal_reminder_notifications_task() -> dict[str, int]:
    from src.notifications.worker import deliver_learning_goal_reminder_notifications

    return await deliver_learning_goal_reminder_notifications()


__all__ = [
    "deliver_daily_digest_notifications_task",
    "deliver_learning_goal_reminder_notifications_task",
    "deliver_weekly_report_notifications_task",
]
