import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class BillingCustomerModel(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "billing_customers"
    __table_args__ = (
        Index("ix_billing_customers_user_id", "user_id", unique=True),
        Index("ix_billing_customers_stripe_customer_id", "stripe_customer_id", unique=True),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    stripe_customer_id: Mapped[str] = mapped_column(String(255), nullable=False)


class SubscriptionModel(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "subscriptions"
    __table_args__ = (
        Index("ix_subscriptions_user_id_created", "user_id", "created_at"),
        Index("ix_subscriptions_stripe_customer_id", "stripe_customer_id"),
        Index("ix_subscriptions_stripe_subscription_id", "stripe_subscription_id", unique=True),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    stripe_customer_id: Mapped[str] = mapped_column(String(255), nullable=False)
    stripe_subscription_id: Mapped[str] = mapped_column(String(255), nullable=False)
    stripe_price_id: Mapped[str | None] = mapped_column(String(255))
    plan: Mapped[str] = mapped_column(String(32), nullable=False, default="free", server_default="free")
    status: Mapped[str] = mapped_column(String(64), nullable=False, default="inactive", server_default="inactive")
    seats: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    current_period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancel_at_period_end: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    subscription_metadata: Mapped[dict[str, object]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default="{}",
    )


class SubscriptionEventModel(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "subscription_events"
    __table_args__ = (Index("ix_subscription_events_stripe_event_id", "stripe_event_id", unique=True),)

    stripe_event_id: Mapped[str] = mapped_column(String(255), nullable=False)
    event_type: Mapped[str] = mapped_column(String(255), nullable=False)
    processed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    event_data: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
