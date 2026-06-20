from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from src.models.notification_delivery import NotificationDeliveryModel

if TYPE_CHECKING:
    from datetime import datetime

    from src.postgres import AsyncSession


@dataclass(slots=True)
class NotificationDeliveryRecord:
    id: UUID
    user_id: UUID
    channel: str
    kind: str
    period_key: str
    target: str
    subject: str
    body: str
    status: str
    last_error: str | None
    sent_at: datetime | None
    skipped_at: datetime | None
    failed_at: datetime | None
    created_at: datetime
    updated_at: datetime | None = None


class NotificationDeliveryRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @classmethod
    def from_session(cls, session: AsyncSession) -> NotificationDeliveryRepository:
        return cls(session)

    async def create_if_absent(
        self,
        *,
        user_id: UUID,
        channel: str,
        kind: str,
        period_key: str,
        target: str,
        subject: str,
        body: str,
    ) -> tuple[NotificationDeliveryRecord, bool]:
        delivery_id = uuid4()
        result = await self._session.execute(
            pg_insert(NotificationDeliveryModel)
            .values(
                id=delivery_id,
                user_id=user_id,
                channel=channel,
                kind=kind,
                period_key=period_key,
                target=target,
                subject=subject,
                body=body,
                status="pending",
            )
            .on_conflict_do_nothing(
                constraint="uq_notification_delivery_period_target",
            )
            .returning(NotificationDeliveryModel)
        )
        model = result.scalar_one_or_none()
        if model is not None:
            return self._to_record(model), True
        existing = await self._get_existing(
            user_id=user_id,
            channel=channel,
            kind=kind,
            period_key=period_key,
            target=target,
        )
        return self._to_record(existing), False

    async def mark_sent(self, delivery_id: UUID, sent_at: datetime) -> NotificationDeliveryRecord:
        model = await self._get_by_id(delivery_id)
        model.status = "sent"
        model.sent_at = sent_at
        model.last_error = None
        await self._session.flush()
        await self._session.refresh(model)
        return self._to_record(model)

    async def mark_skipped(self, delivery_id: UUID, skipped_at: datetime, reason: str) -> NotificationDeliveryRecord:
        model = await self._get_by_id(delivery_id)
        model.status = "skipped"
        model.skipped_at = skipped_at
        model.last_error = reason[:1000]
        await self._session.flush()
        await self._session.refresh(model)
        return self._to_record(model)

    async def mark_failed(self, delivery_id: UUID, failed_at: datetime, error: str) -> NotificationDeliveryRecord:
        model = await self._get_by_id(delivery_id)
        model.status = "failed"
        model.failed_at = failed_at
        model.last_error = error[:1000]
        await self._session.flush()
        await self._session.refresh(model)
        return self._to_record(model)

    async def _get_by_id(self, delivery_id: UUID) -> NotificationDeliveryModel:
        result = await self._session.execute(
            select(NotificationDeliveryModel).where(NotificationDeliveryModel.id == delivery_id)
        )
        return result.scalar_one()

    async def _get_existing(
        self,
        *,
        user_id: UUID,
        channel: str,
        kind: str,
        period_key: str,
        target: str,
    ) -> NotificationDeliveryModel:
        result = await self._session.execute(
            select(NotificationDeliveryModel).where(
                NotificationDeliveryModel.user_id == user_id,
                NotificationDeliveryModel.channel == channel,
                NotificationDeliveryModel.kind == kind,
                NotificationDeliveryModel.period_key == period_key,
                NotificationDeliveryModel.target == target,
            )
        )
        return result.scalar_one()

    @staticmethod
    def _to_record(model: NotificationDeliveryModel) -> NotificationDeliveryRecord:
        return NotificationDeliveryRecord(
            id=model.id,
            user_id=model.user_id,
            channel=model.channel,
            kind=model.kind,
            period_key=model.period_key,
            target=model.target,
            subject=model.subject,
            body=model.body,
            status=model.status,
            last_error=model.last_error,
            sent_at=model.sent_at,
            skipped_at=model.skipped_at,
            failed_at=model.failed_at,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )


__all__ = [
    "NotificationDeliveryRecord",
    "NotificationDeliveryRepository",
]
