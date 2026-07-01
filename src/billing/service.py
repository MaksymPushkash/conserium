from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, cast
from urllib.parse import urljoin, urlparse
from uuid import UUID

import stripe

from src.billing.repository import BillingRepository
from src.billing.schemas import (
    BillingCheckoutRequest,
    BillingCheckoutResponse,
    BillingEntitlementsResponse,
    BillingPlan,
    BillingPortalRequest,
    BillingPortalResponse,
    BillingStatus,
    BillingSubscriptionResponse,
)
from src.billing.webhooks import parse_stripe_event
from src.documents.document_repository import DocumentRepository
from src.kit.exceptions import ResourceNotFoundException, ValidationException
from src.models.billing import BillingCustomerModel, SubscriptionModel
from src.postgres import AsyncReadSession, AsyncSession
from src.settings import settings
from src.workspaces.repository import SharedWorkspaceRepository

PAID_STATUSES = {"active", "trialing"}
KNOWN_STATUSES = {
    "inactive",
    "incomplete",
    "incomplete_expired",
    "trialing",
    "active",
    "past_due",
    "canceled",
    "unpaid",
    "paused",
}


class BillingService:
    async def subscription(self, session: AsyncReadSession, *, user_id: UUID) -> BillingSubscriptionResponse:
        subscription = await BillingRepository.from_session(session).latest_subscription_for_user(user_id)
        return await self._subscription_response(session, user_id=user_id, subscription=subscription)

    async def create_checkout(
        self,
        session: AsyncSession,
        *,
        user_id: UUID,
        email: str,
        body: BillingCheckoutRequest,
    ) -> BillingCheckoutResponse:
        price_id = _price_id_for_plan(body.plan)
        if not price_id:
            raise ValidationException(f"Stripe price id is not configured for {body.plan}")
        _configure_stripe()

        success_url = _safe_frontend_url(
            body.success_url,
            fallback="/settings#billing?checkout=success",
            field_name="success_url",
        )
        cancel_url = _safe_frontend_url(
            body.cancel_url,
            fallback="/settings#billing?checkout=cancelled",
            field_name="cancel_url",
        )
        customer = await self._get_or_create_customer(session, user_id=user_id, email=email)
        metadata = {
            "user_id": str(user_id),
            "plan": body.plan,
        }
        if body.workspace_id:
            metadata["workspace_id"] = str(body.workspace_id)

        checkout_session = cast(
            "Any",
            stripe.checkout.Session.create(
                mode="subscription",
                customer=customer.stripe_customer_id,
                client_reference_id=str(user_id),
                line_items=[{"price": price_id, "quantity": _checkout_quantity(body.plan, body.seats)}],
                success_url=success_url,
                cancel_url=cancel_url,
                metadata=metadata,
                subscription_data={"metadata": metadata},
            ),
        )
        url = _string(getattr(checkout_session, "url", None))
        if not url:
            raise ValidationException("Stripe did not return a checkout URL")
        return BillingCheckoutResponse(url=url)

    async def create_portal(
        self,
        session: AsyncSession,
        *,
        user_id: UUID,
        email: str,
        body: BillingPortalRequest,
    ) -> BillingPortalResponse:
        _configure_stripe()
        return_url = _safe_frontend_url(body.return_url, fallback="/settings#billing", field_name="return_url")
        customer = await self._get_or_create_customer(session, user_id=user_id, email=email)
        portal_session = cast(
            "Any",
            stripe.billing_portal.Session.create(
                customer=customer.stripe_customer_id,
                return_url=return_url,
            ),
        )
        url = _string(getattr(portal_session, "url", None))
        if not url:
            raise ValidationException("Stripe did not return a billing portal URL")
        return BillingPortalResponse(url=url)

    async def handle_webhook(self, session: AsyncSession, *, body: bytes, stripe_signature: str | None) -> None:
        event = parse_stripe_event(body, stripe_signature)
        repository = BillingRepository.from_session(session)
        event_id = str(event["id"])
        event_type = str(event["type"])
        if not await repository.reserve_event(
            stripe_event_id=event_id,
            event_type=event_type,
            event_data=cast("dict[str, object]", event),
        ):
            return

        event_object = cast("dict[str, Any]", cast("dict[str, Any]", event["data"])["object"])
        if event_type == "checkout.session.completed":
            await self._handle_checkout_completed(session, event_object)
        elif event_type in {
            "customer.subscription.created",
            "customer.subscription.updated",
            "customer.subscription.deleted",
        }:
            await self._handle_subscription_event(session, event_object)
        elif event_type == "invoice.payment_failed":
            await self._mark_invoice_subscription(session, event_object, status="past_due")
        elif event_type == "invoice.paid":
            await self._mark_invoice_subscription(session, event_object, status="active")

    async def can_create_document(self, session: AsyncReadSession, *, user_id: UUID) -> bool:
        entitlements = await self.entitlements(session, user_id=user_id)
        return entitlements.can_create_document

    async def ensure_can_create_document(self, session: AsyncReadSession, *, user_id: UUID) -> None:
        if not await self.can_create_document(session, user_id=user_id):
            raise ValidationException("Free plan document limit reached. Upgrade to Pro for unlimited documents.")

    async def can_create_api_key(self, session: AsyncReadSession, *, user_id: UUID) -> bool:
        entitlements = await self.entitlements(session, user_id=user_id)
        return entitlements.can_create_api_key

    async def ensure_can_create_api_key(self, session: AsyncReadSession, *, user_id: UUID) -> None:
        if not await self.can_create_api_key(session, user_id=user_id):
            raise ValidationException("API keys require Pro or Team billing.")

    async def has_priority_processing(self, session: AsyncReadSession, *, user_id: UUID) -> bool:
        entitlements = await self.entitlements(session, user_id=user_id)
        return entitlements.priority_processing

    async def workspace_member_limit(self, session: AsyncReadSession, *, workspace_id: UUID) -> int | None:
        workspace = await SharedWorkspaceRepository.from_session(session).get_workspace(workspace_id=workspace_id)
        if workspace is None:
            raise ResourceNotFoundException("workspace not found")
        return await self.member_limit_for_user(session, user_id=workspace.user_id)

    async def member_limit_for_user(self, session: AsyncReadSession, *, user_id: UUID) -> int | None:
        subscription = await BillingRepository.from_session(session).latest_subscription_for_user(user_id)
        return _workspace_member_limit(subscription)

    async def entitlements(self, session: AsyncReadSession, *, user_id: UUID) -> BillingEntitlementsResponse:
        subscription = await BillingRepository.from_session(session).latest_subscription_for_user(user_id)
        plan = _effective_plan(subscription)
        documents_used = await DocumentRepository.from_session(session).count_by_user_id(user_id)
        document_limit = None if plan in {"pro", "team"} else settings.BILLING_FREE_DOCUMENT_LIMIT
        return BillingEntitlementsResponse(
            plan=plan,
            documents_used=documents_used,
            document_limit=document_limit,
            can_create_document=document_limit is None or documents_used < document_limit,
            can_create_api_key=plan in {"pro", "team"},
            priority_processing=plan in {"pro", "team"},
            workspace_member_limit=_workspace_member_limit(subscription),
        )

    async def _subscription_response(
        self,
        session: AsyncReadSession,
        *,
        user_id: UUID,
        subscription: SubscriptionModel | None,
    ) -> BillingSubscriptionResponse:
        entitlements = await self.entitlements(session, user_id=user_id)
        status = subscription.status if subscription else "inactive"
        if status not in KNOWN_STATUSES:
            status = "inactive"
        return BillingSubscriptionResponse(
            plan=entitlements.plan,
            status=cast("BillingStatus", status),
            seats=subscription.seats if subscription else 1,
            stripe_price_id=subscription.stripe_price_id if subscription else None,
            current_period_end=subscription.current_period_end if subscription else None,
            cancel_at_period_end=subscription.cancel_at_period_end if subscription else False,
            entitlements=entitlements,
        )

    async def _get_or_create_customer(
        self,
        session: AsyncSession,
        *,
        user_id: UUID,
        email: str,
    ) -> BillingCustomerModel:
        repository = BillingRepository.from_session(session)
        customer = await repository.get_customer_by_user_id(user_id)
        if customer is not None:
            return customer

        stripe_customer = stripe.Customer.create(email=email, metadata={"user_id": str(user_id)})
        stripe_customer_id = cast("str", stripe_customer["id"])
        return await repository.create_customer(user_id=user_id, stripe_customer_id=stripe_customer_id)

    async def _handle_checkout_completed(self, session: AsyncSession, event_object: dict[str, Any]) -> None:
        subscription_id = _string(event_object.get("subscription"))
        customer_id = _string(event_object.get("customer"))
        user_id = _uuid(_string(event_object.get("client_reference_id")))
        if not subscription_id or not customer_id or user_id is None:
            return
        stripe_subscription = stripe.Subscription.retrieve(subscription_id)
        await self._upsert_from_stripe_subscription(
            session,
            user_id=user_id,
            stripe_customer_id=customer_id,
            stripe_subscription=cast("dict[str, Any]", stripe_subscription),
        )

    async def _handle_subscription_event(self, session: AsyncSession, event_object: dict[str, Any]) -> None:
        customer_id = _string(event_object.get("customer"))
        if not customer_id:
            return
        customer = await BillingRepository.from_session(session).get_customer_by_stripe_id(customer_id)
        if customer is None:
            return
        await self._upsert_from_stripe_subscription(
            session,
            user_id=customer.user_id,
            stripe_customer_id=customer_id,
            stripe_subscription=event_object,
        )

    async def _mark_invoice_subscription(
        self,
        session: AsyncSession,
        event_object: dict[str, Any],
        *,
        status: str,
    ) -> None:
        subscription_id = _string(event_object.get("subscription"))
        if not subscription_id:
            return
        repository = BillingRepository.from_session(session)
        subscription = await repository.subscription_by_stripe_id(subscription_id)
        if subscription is None:
            return
        await repository.upsert_subscription(
            user_id=subscription.user_id,
            stripe_customer_id=subscription.stripe_customer_id,
            stripe_subscription_id=subscription.stripe_subscription_id,
            stripe_price_id=subscription.stripe_price_id,
            plan=subscription.plan,
            status=status,
            seats=subscription.seats,
            current_period_end=subscription.current_period_end,
            cancel_at_period_end=subscription.cancel_at_period_end,
            subscription_metadata=subscription.subscription_metadata,
        )

    async def _upsert_from_stripe_subscription(
        self,
        session: AsyncSession,
        *,
        user_id: UUID,
        stripe_customer_id: str,
        stripe_subscription: dict[str, Any],
    ) -> None:
        item = _first_subscription_item(stripe_subscription)
        price_id = _string(cast("dict[str, Any]", item.get("price", {})).get("id")) if item else None
        plan = _plan_for_price_id(price_id)
        seats = int(item.get("quantity") or 1) if item else 1
        status = _string(stripe_subscription.get("status")) or "inactive"
        current_period_end = _timestamp(stripe_subscription.get("current_period_end"))
        metadata = cast("dict[str, object]", stripe_subscription.get("metadata") or {})
        await BillingRepository.from_session(session).upsert_subscription(
            user_id=user_id,
            stripe_customer_id=stripe_customer_id,
            stripe_subscription_id=cast("str", stripe_subscription["id"]),
            stripe_price_id=price_id,
            plan=plan,
            status=status,
            seats=seats,
            current_period_end=current_period_end,
            cancel_at_period_end=bool(stripe_subscription.get("cancel_at_period_end") or False),
            subscription_metadata=metadata,
        )


def _configure_stripe() -> None:
    stripe.api_key = settings.STRIPE_SECRET_KEY
    if not stripe.api_key:
        raise ValidationException("Stripe is not configured")


def _price_id_for_plan(plan: str) -> str:
    if plan == "pro":
        return settings.STRIPE_PRO_PRICE_ID
    if plan == "team":
        return settings.STRIPE_TEAM_PRICE_ID
    return ""


def _plan_for_price_id(price_id: str | None) -> BillingPlan:
    if price_id and price_id == settings.STRIPE_TEAM_PRICE_ID:
        return "team"
    if price_id and price_id == settings.STRIPE_PRO_PRICE_ID:
        return "pro"
    return "free"


def _effective_plan(subscription: SubscriptionModel | None) -> BillingPlan:
    if subscription is None or subscription.status not in PAID_STATUSES:
        return "free"
    if subscription.plan == "team":
        return "team"
    if subscription.plan == "pro":
        return "pro"
    return "free"


def _checkout_quantity(plan: BillingPlan, seats: int) -> int:
    if plan == "team":
        return max(seats, 1)
    return 1


def _workspace_member_limit(subscription: SubscriptionModel | None) -> int:
    plan = _effective_plan(subscription)
    if plan == "team":
        return max(subscription.seats if subscription else 1, 1)
    if plan == "pro":
        return 5
    return 3


def _safe_frontend_url(value: str | None, *, fallback: str, field_name: str) -> str:
    frontend = settings.FRONTEND_URL.rstrip("/") + "/"
    frontend_parts = urlparse(frontend)
    if not frontend_parts.scheme or not frontend_parts.netloc:
        raise ValidationException("Frontend URL is not configured")

    if not value:
        return urljoin(frontend, fallback.lstrip("/"))
    if value.startswith("/") and not value.startswith("//"):
        return urljoin(frontend, value.lstrip("/"))

    parsed = urlparse(value)
    if parsed.scheme in {"http", "https"} and parsed.netloc == frontend_parts.netloc:
        return value
    raise ValidationException(f"{field_name} must use the configured frontend origin")


def _first_subscription_item(stripe_subscription: dict[str, Any]) -> dict[str, Any] | None:
    items = cast("dict[str, Any]", stripe_subscription.get("items") or {})
    data = items.get("data") or []
    if not isinstance(data, list) or not data:
        return None
    return cast("dict[str, Any]", data[0])


def _string(value: object) -> str | None:
    if isinstance(value, str) and value:
        return value
    return None


def _uuid(value: str | None) -> UUID | None:
    if not value:
        return None
    try:
        return UUID(value)
    except ValueError:
        return None


def _timestamp(value: object) -> datetime | None:
    if isinstance(value, int | float):
        return datetime.fromtimestamp(value, tz=UTC)
    return None


billing = BillingService()

__all__ = [
    "BillingService",
    "billing",
]
