from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Self, cast

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from src.models.billing import BillingCustomerModel, SubscriptionEventModel, SubscriptionModel

if TYPE_CHECKING:
    from src.postgres import AsyncSession


class BillingRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @classmethod
    def from_session(cls, session: AsyncSession) -> Self:
        return cls(session)

    async def get_customer_by_user_id(self, user_id: uuid.UUID) -> BillingCustomerModel | None:
        return cast(
            "BillingCustomerModel | None",
            await self._session.scalar(select(BillingCustomerModel).where(BillingCustomerModel.user_id == user_id)),
        )

    async def get_customer_by_stripe_id(self, stripe_customer_id: str) -> BillingCustomerModel | None:
        return cast(
            "BillingCustomerModel | None",
            await self._session.scalar(
                select(BillingCustomerModel).where(BillingCustomerModel.stripe_customer_id == stripe_customer_id)
            ),
        )

    async def create_customer(self, *, user_id: uuid.UUID, stripe_customer_id: str) -> BillingCustomerModel:
        model = BillingCustomerModel(
            id=uuid.uuid4(),
            user_id=user_id,
            stripe_customer_id=stripe_customer_id,
        )
        self._session.add(model)
        await self._session.flush()
        return model

    async def latest_subscription_for_user(self, user_id: uuid.UUID) -> SubscriptionModel | None:
        return cast(
            "SubscriptionModel | None",
            await self._session.scalar(
                select(SubscriptionModel)
                .where(SubscriptionModel.user_id == user_id)
                .order_by(SubscriptionModel.created_at.desc())
                .limit(1)
            ),
        )

    async def subscription_by_stripe_id(self, stripe_subscription_id: str) -> SubscriptionModel | None:
        return cast(
            "SubscriptionModel | None",
            await self._session.scalar(
                select(SubscriptionModel).where(SubscriptionModel.stripe_subscription_id == stripe_subscription_id)
            ),
        )

    async def upsert_subscription(
        self,
        *,
        user_id: uuid.UUID,
        stripe_customer_id: str,
        stripe_subscription_id: str,
        stripe_price_id: str | None,
        plan: str,
        status: str,
        seats: int,
        current_period_end: datetime | None,
        cancel_at_period_end: bool,
        subscription_metadata: dict[str, object],
    ) -> SubscriptionModel:
        model = await self.subscription_by_stripe_id(stripe_subscription_id)
        if model is None:
            model = SubscriptionModel(
                id=uuid.uuid4(),
                user_id=user_id,
                stripe_customer_id=stripe_customer_id,
                stripe_subscription_id=stripe_subscription_id,
            )
            self._session.add(model)
        model.stripe_price_id = stripe_price_id
        model.plan = plan
        model.status = status
        model.seats = seats
        model.current_period_end = current_period_end
        model.cancel_at_period_end = cancel_at_period_end
        model.subscription_metadata = subscription_metadata
        await self._session.flush()
        return model

    async def reserve_event(
        self,
        *,
        stripe_event_id: str,
        event_type: str,
        event_data: dict[str, object],
    ) -> bool:
        statement = (
            insert(SubscriptionEventModel)
            .values(
                id=uuid.uuid4(),
                stripe_event_id=stripe_event_id,
                event_type=event_type,
                processed_at=datetime.now(UTC),
                event_data=event_data,
            )
            .on_conflict_do_nothing(index_elements=["stripe_event_id"])
            .returning(SubscriptionEventModel.id)
        )
        result = await self._session.execute(statement)
        return result.scalar_one_or_none() is not None
