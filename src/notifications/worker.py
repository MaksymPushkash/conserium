from __future__ import annotations

from src.notifications.service import (
    DailyDigestDelivery,
    LearningGoalReminderDelivery,
    ProactiveDeliveryResult,
    WeeklyReportDelivery,
)
from src.notifications.telegram_sender import TelegramNotificationSender
from src.worker.dependencies import get_worker_session_factory


async def deliver_daily_digest_notifications(*, limit: int = 500) -> dict[str, int]:
    factory = get_worker_session_factory()
    async with factory() as session:
        result = await DailyDigestDelivery(
            session,
            TelegramNotificationSender(),
        )(limit=limit)
    return _delivery_result(result)


async def deliver_weekly_report_notifications(*, limit: int = 500) -> dict[str, int]:
    factory = get_worker_session_factory()
    async with factory() as session:
        result = await WeeklyReportDelivery(
            session,
            TelegramNotificationSender(),
        )(limit=limit)
    return _delivery_result(result)


async def deliver_learning_goal_reminder_notifications(*, limit: int = 500) -> dict[str, int]:
    factory = get_worker_session_factory()
    async with factory() as session:
        result = await LearningGoalReminderDelivery(
            session,
            TelegramNotificationSender(),
        )(limit=limit)
    return _delivery_result(result)


def _delivery_result(result: ProactiveDeliveryResult) -> dict[str, int]:
    return {
        "candidates": int(result.candidates),
        "created": int(result.created),
        "sent": int(result.sent),
        "skipped": int(result.skipped),
        "failed": int(result.failed),
        "duplicate": int(result.duplicate),
    }
