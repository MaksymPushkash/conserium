from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field

from src.kit.schemas import Schema

BillingPlan = Literal["free", "pro", "team"]
BillingStatus = Literal[
    "inactive",
    "incomplete",
    "incomplete_expired",
    "trialing",
    "active",
    "past_due",
    "canceled",
    "unpaid",
    "paused",
]


class BillingCheckoutRequest(Schema):
    plan: Literal["pro", "team"]
    seats: int = Field(default=1, ge=1, le=100)
    success_url: str | None = Field(default=None, max_length=2000)
    cancel_url: str | None = Field(default=None, max_length=2000)
    workspace_id: UUID | None = None


class BillingCheckoutResponse(Schema):
    url: str


class BillingPortalRequest(Schema):
    return_url: str | None = Field(default=None, max_length=2000)


class BillingPortalResponse(Schema):
    url: str


class BillingEntitlementsResponse(Schema):
    plan: BillingPlan
    documents_used: int
    document_limit: int | None
    can_create_document: bool
    can_create_api_key: bool
    priority_processing: bool
    workspace_member_limit: int | None


class BillingSubscriptionResponse(Schema):
    plan: BillingPlan
    status: BillingStatus
    seats: int
    stripe_price_id: str | None
    current_period_end: datetime | None
    cancel_at_period_end: bool
    entitlements: BillingEntitlementsResponse
