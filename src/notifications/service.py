from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import TYPE_CHECKING

from src.integrations.repository import TelegramRepository
from src.kit.ports.notifications import INotificationSender, NotificationDeliveryUnavailable
from src.learning_goals.repository import LearningGoalRepository
from src.notifications.repository import NotificationDeliveryRepository
from src.stats.repository import StatsRepository
from src.stats.service import _recommended_actions, _summary

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable
    from uuid import UUID

    from src.integrations.repository import TelegramChatBindingRecord
    from src.postgres import AsyncSession


@dataclass(slots=True)
class ProactiveDeliveryResult:
    candidates: int = 0
    created: int = 0
    sent: int = 0
    skipped: int = 0
    failed: int = 0
    duplicate: int = 0


class DailyDigestDelivery:
    def __init__(self, session: AsyncSession, sender: INotificationSender) -> None:
        self._runner = _TelegramDeliveryRunner(session, sender)

    async def __call__(self, *, now: datetime | None = None, limit: int = 500) -> ProactiveDeliveryResult:
        current = now or datetime.now(UTC)
        return await self._runner.deliver(
            kind="daily_digest",
            period_key=current.date().isoformat(),
            limit=limit,
            compose=self._compose,
        )

    async def _compose(self, user_id: UUID) -> tuple[str, str] | None:
        items = await StatsRepository.from_session(self._runner.session).get_daily_digest_items(user_id=user_id, limit=3)
        if not items:
            return None
        lines = ["Daily digest", ""]
        for index, item in enumerate(items, start=1):
            reason = f" - {item.reason}" if item.reason else ""
            lines.append(f"{index}. {item.title}{reason}")
            if item.question:
                lines.append(f"   Ask: {item.question}")
        return "Conserium daily digest", "\n".join(lines)


class WeeklyReportDelivery:
    def __init__(self, session: AsyncSession, sender: INotificationSender) -> None:
        self._runner = _TelegramDeliveryRunner(session, sender)

    async def __call__(self, *, now: datetime | None = None, limit: int = 500) -> ProactiveDeliveryResult:
        current = now or datetime.now(UTC)
        year, week, _ = current.isocalendar()
        return await self._runner.deliver(
            kind="weekly_report",
            period_key=f"{year}-W{week:02d}",
            limit=limit,
            compose=self._compose,
        )

    async def _compose(self, user_id: UUID) -> tuple[str, str] | None:
        report = await StatsRepository.from_session(self._runner.session).get_weekly_report(user_id=user_id)
        actions = _recommended_actions(
            stale_documents=report.stale_documents,
            failed_documents=report.failed_documents,
            query_count=report.query_count,
            saved_documents=report.saved_documents,
        )
        lines = [
            "Weekly report",
            "",
            _summary(report.saved_documents, report.active_documents, report.query_count),
            f"Ready sources: {report.ready_documents}",
            f"Failed sources: {report.failed_documents}",
            f"Stale sources: {report.stale_documents}",
            "",
            "Next actions:",
            *[f"- {action}" for action in actions],
        ]
        return "Conserium weekly report", "\n".join(lines)


class LearningGoalReminderDelivery:
    def __init__(self, session: AsyncSession, sender: INotificationSender) -> None:
        self._runner = _TelegramDeliveryRunner(session, sender)

    async def __call__(self, *, now: datetime | None = None, limit: int = 500) -> ProactiveDeliveryResult:
        current = now or datetime.now(UTC)
        return await self._runner.deliver(
            kind="learning_goal_reminder",
            period_key=current.date().isoformat(),
            limit=limit,
            compose=lambda user_id: self._compose(user_id, today=current.date()),
        )

    async def _compose(self, user_id: UUID, *, today: date) -> tuple[str, str] | None:
        goals = await LearningGoalRepository.from_session(self._runner.session).list_by_user_id(user_id)
        due: list[tuple[str, date]] = []
        for goal in goals:
            target_date = goal.target_date
            if goal.status != "active" or target_date is None:
                continue
            if target_date <= today + timedelta(days=3):
                due.append((goal.topic, target_date))
        if not due:
            return None
        lines = ["Learning goal reminders", ""]
        for topic, target_date in due[:5]:
            if target_date < today:
                state = "overdue"
            elif target_date == today:
                state = "due today"
            else:
                state = f"due {target_date.isoformat()}"
            lines.append(f"- {topic}: {state}")
        return "Conserium goal reminders", "\n".join(lines)


class _TelegramDeliveryRunner:
    def __init__(self, session: AsyncSession, sender: INotificationSender) -> None:
        self.session = session
        self._sender = sender

    async def deliver(
        self,
        *,
        kind: str,
        period_key: str,
        limit: int,
        compose: Callable[[UUID], Awaitable[tuple[str, str] | None]],
    ) -> ProactiveDeliveryResult:
        result = ProactiveDeliveryResult()
        bindings = await self._active_bindings(limit=limit)
        result.candidates = len(bindings)
        for binding in bindings:
            message = await compose(binding.user_id)
            if message is None:
                result.skipped += 1
                continue
            subject, body = message
            created = await self._create_delivery(binding, kind=kind, period_key=period_key, subject=subject, body=body)
            if created is None:
                result.duplicate += 1
                continue
            result.created += 1
            try:
                await self._sender.send_telegram(chat_id=binding.chat_id, subject=subject, body=body)
            except NotificationDeliveryUnavailable as exc:
                await self._mark_skipped(created, str(exc))
                result.skipped += 1
            except Exception as exc:
                await self._mark_failed(created, str(exc))
                result.failed += 1
            else:
                await self._mark_sent(created)
                result.sent += 1
        return result

    async def _active_bindings(self, *, limit: int) -> list[TelegramChatBindingRecord]:
        return await TelegramRepository.from_session(self.session).list_active_bindings(limit=limit)

    async def _create_delivery(
        self,
        binding: TelegramChatBindingRecord,
        *,
        kind: str,
        period_key: str,
        subject: str,
        body: str,
    ) -> UUID | None:
        try:
            delivery, created = await NotificationDeliveryRepository.from_session(self.session).create_if_absent(
                user_id=binding.user_id,
                channel="telegram",
                kind=kind,
                period_key=period_key,
                target=binding.chat_id,
                subject=subject,
                body=body,
            )
            await self.session.commit()
        except Exception:
            await self.session.rollback()
            raise
        return delivery.id if created else None

    async def _mark_sent(self, delivery_id: UUID) -> None:
        try:
            await NotificationDeliveryRepository.from_session(self.session).mark_sent(delivery_id, datetime.now(UTC))
            await self.session.commit()
        except Exception:
            await self.session.rollback()
            raise

    async def _mark_skipped(self, delivery_id: UUID, reason: str) -> None:
        try:
            await NotificationDeliveryRepository.from_session(self.session).mark_skipped(
                delivery_id, datetime.now(UTC), reason
            )
            await self.session.commit()
        except Exception:
            await self.session.rollback()
            raise

    async def _mark_failed(self, delivery_id: UUID, error: str) -> None:
        try:
            await NotificationDeliveryRepository.from_session(self.session).mark_failed(
                delivery_id, datetime.now(UTC), error
            )
            await self.session.commit()
        except Exception:
            await self.session.rollback()
            raise



__all__ = [
    "DailyDigestDelivery",
    "LearningGoalReminderDelivery",
    "ProactiveDeliveryResult",
    "WeeklyReportDelivery",
]
