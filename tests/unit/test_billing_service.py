import json
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

from src.billing.repository import BillingRepository
from src.billing.schemas import BillingCheckoutRequest, BillingPortalRequest
from src.billing.service import BillingService
from src.documents.document_repository import DocumentRepository
from src.kit.exceptions import ValidationException
from src.models.billing import BillingCustomerModel, SubscriptionModel


@pytest.mark.asyncio
async def test_free_plan_document_limit_blocks_creation(monkeypatch: pytest.MonkeyPatch) -> None:
    user_id = uuid4()
    billing_repo = _BillingRepo(subscription=None)
    monkeypatch.setattr(BillingRepository, "from_session", classmethod(lambda cls, session: billing_repo))
    monkeypatch.setattr(DocumentRepository, "from_session", classmethod(lambda cls, session: _DocumentCountRepo(count=50)))

    service = BillingService()

    assert await service.can_create_document(_FakeSession(), user_id=user_id) is False
    with pytest.raises(ValidationException):
        await service.ensure_can_create_document(_FakeSession(), user_id=user_id)


@pytest.mark.asyncio
async def test_paid_plan_allows_api_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    user_id = uuid4()
    subscription = _subscription(user_id=user_id, plan="pro", status="active")
    monkeypatch.setattr(BillingRepository, "from_session", classmethod(lambda cls, session: _BillingRepo(subscription=subscription)))
    monkeypatch.setattr(DocumentRepository, "from_session", classmethod(lambda cls, session: _DocumentCountRepo(count=500)))

    service = BillingService()

    assert await service.can_create_api_key(_FakeSession(), user_id=user_id) is True
    await service.ensure_can_create_api_key(_FakeSession(), user_id=user_id)


@pytest.mark.asyncio
async def test_checkout_and_portal_create_stripe_sessions(monkeypatch: pytest.MonkeyPatch) -> None:
    user_id = uuid4()
    billing_repo = _BillingRepo(subscription=None)
    checkout_calls: list[dict[str, object]] = []
    portal_calls: list[dict[str, object]] = []
    monkeypatch.setattr(BillingRepository, "from_session", classmethod(lambda cls, session: billing_repo))
    monkeypatch.setattr("src.billing.service.settings.STRIPE_SECRET_KEY", "sk_test_123")
    monkeypatch.setattr("src.billing.service.settings.STRIPE_PRO_PRICE_ID", "price_pro")
    monkeypatch.setattr("src.billing.service.settings.FRONTEND_URL", "http://localhost:3000")
    monkeypatch.setattr("src.billing.service.stripe.Customer.create", lambda **kwargs: {"id": "cus_123"})

    def create_checkout_session(**kwargs: object) -> SimpleNamespace:
        checkout_calls.append(kwargs)
        return SimpleNamespace(url="https://checkout.stripe.test/session")

    def create_portal_session(**kwargs: object) -> SimpleNamespace:
        portal_calls.append(kwargs)
        return SimpleNamespace(url="https://billing.stripe.test/session")

    monkeypatch.setattr("src.billing.service.stripe.checkout.Session.create", create_checkout_session)
    monkeypatch.setattr("src.billing.service.stripe.billing_portal.Session.create", create_portal_session)

    service = BillingService()
    checkout = await service.create_checkout(
        _FakeSession(),
        user_id=user_id,
        email="user@example.test",
        body=BillingCheckoutRequest(plan="pro"),
    )
    portal = await service.create_portal(
        _FakeSession(),
        user_id=user_id,
        email="user@example.test",
        body=BillingPortalRequest(),
    )

    assert checkout.url == "https://checkout.stripe.test/session"
    assert portal.url == "https://billing.stripe.test/session"
    assert checkout_calls[0]["success_url"] == "http://localhost:3000/settings#billing?checkout=success"
    assert portal_calls[0]["return_url"] == "http://localhost:3000/settings#billing"
    assert billing_repo.customer is not None
    assert billing_repo.customer.stripe_customer_id == "cus_123"


@pytest.mark.asyncio
async def test_checkout_and_portal_reject_external_return_urls(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(BillingRepository, "from_session", classmethod(lambda cls, session: _BillingRepo(subscription=None)))
    monkeypatch.setattr("src.billing.service.settings.STRIPE_SECRET_KEY", "sk_test_123")
    monkeypatch.setattr("src.billing.service.settings.STRIPE_PRO_PRICE_ID", "price_pro")
    monkeypatch.setattr("src.billing.service.settings.FRONTEND_URL", "http://localhost:3000")

    service = BillingService()

    with pytest.raises(ValidationException, match="success_url"):
        await service.create_checkout(
            _FakeSession(),
            user_id=uuid4(),
            email="user@example.test",
            body=BillingCheckoutRequest(plan="pro", success_url="https://evil.example/success"),
        )

    with pytest.raises(ValidationException, match="return_url"):
        await service.create_portal(
            _FakeSession(),
            user_id=uuid4(),
            email="user@example.test",
            body=BillingPortalRequest(return_url="https://evil.example/settings"),
        )


@pytest.mark.asyncio
async def test_team_member_limit_uses_stripe_subscription_quantity(monkeypatch: pytest.MonkeyPatch) -> None:
    user_id = uuid4()
    subscription = _subscription(user_id=user_id, plan="team", status="active", seats=7)
    monkeypatch.setattr(BillingRepository, "from_session", classmethod(lambda cls, session: _BillingRepo(subscription=subscription)))
    monkeypatch.setattr(DocumentRepository, "from_session", classmethod(lambda cls, session: _DocumentCountRepo(count=10)))

    service = BillingService()

    assert await service.member_limit_for_user(_FakeSession(), user_id=user_id) == 7
    entitlements = await service.entitlements(_FakeSession(), user_id=user_id)
    assert entitlements.workspace_member_limit == 7


@pytest.mark.asyncio
async def test_webhook_event_processing_is_idempotent(monkeypatch: pytest.MonkeyPatch) -> None:
    billing_repo = _BillingRepo(subscription=None)
    monkeypatch.setattr(BillingRepository, "from_session", classmethod(lambda cls, session: billing_repo))
    monkeypatch.setattr("src.billing.service.settings.DEBUG", True)
    monkeypatch.setattr("src.billing.service.settings.STRIPE_WEBHOOK_SECRET", "")
    event = {
        "id": "evt_123",
        "type": "invoice.paid",
        "data": {"object": {"subscription": "sub_missing"}},
    }

    service = BillingService()
    body = json.dumps(event).encode()
    await service.handle_webhook(_FakeSession(), body=body, stripe_signature=None)
    await service.handle_webhook(_FakeSession(), body=body, stripe_signature=None)

    assert billing_repo.recorded_events == ["evt_123"]


@pytest.mark.asyncio
async def test_subscription_webhook_updates_and_deletes_subscription(monkeypatch: pytest.MonkeyPatch) -> None:
    user_id = uuid4()
    billing_repo = _BillingRepo(subscription=None)
    billing_repo.customer = BillingCustomerModel(id=uuid4(), user_id=user_id, stripe_customer_id="cus_123")
    monkeypatch.setattr(BillingRepository, "from_session", classmethod(lambda cls, session: billing_repo))
    monkeypatch.setattr("src.billing.service.settings.DEBUG", True)
    monkeypatch.setattr("src.billing.service.settings.STRIPE_WEBHOOK_SECRET", "")
    monkeypatch.setattr("src.billing.service.settings.STRIPE_TEAM_PRICE_ID", "price_team")
    event = {
        "id": "evt_sub_updated",
        "type": "customer.subscription.updated",
        "data": {
            "object": {
                "id": "sub_123",
                "customer": "cus_123",
                "status": "active",
                "current_period_end": 1_735_689_600,
                "cancel_at_period_end": False,
                "metadata": {"workspace_id": "workspace_123"},
                "items": {"data": [{"quantity": 4, "price": {"id": "price_team"}}]},
            }
        },
    }

    service = BillingService()
    await service.handle_webhook(_FakeSession(), body=json.dumps(event).encode(), stripe_signature=None)

    assert billing_repo.subscription is not None
    assert billing_repo.subscription.plan == "team"
    assert billing_repo.subscription.status == "active"
    assert billing_repo.subscription.seats == 4

    deleted = {
        **event,
        "id": "evt_sub_deleted",
        "type": "customer.subscription.deleted",
        "data": {"object": {**event["data"]["object"], "status": "canceled"}},
    }
    await service.handle_webhook(_FakeSession(), body=json.dumps(deleted).encode(), stripe_signature=None)

    assert billing_repo.subscription.status == "canceled"


@pytest.mark.asyncio
async def test_invoice_payment_failed_marks_subscription_past_due(monkeypatch: pytest.MonkeyPatch) -> None:
    user_id = uuid4()
    subscription = _subscription(user_id=user_id, plan="pro", status="active")
    billing_repo = _BillingRepo(subscription=subscription)
    monkeypatch.setattr(BillingRepository, "from_session", classmethod(lambda cls, session: billing_repo))
    monkeypatch.setattr("src.billing.service.settings.DEBUG", True)
    monkeypatch.setattr("src.billing.service.settings.STRIPE_WEBHOOK_SECRET", "")
    event = {
        "id": "evt_invoice_failed",
        "type": "invoice.payment_failed",
        "data": {"object": {"subscription": "sub_123"}},
    }

    service = BillingService()
    await service.handle_webhook(_FakeSession(), body=json.dumps(event).encode(), stripe_signature=None)

    assert billing_repo.subscription is not None
    assert billing_repo.subscription.status == "past_due"


class _FakeSession:
    async def flush(self) -> None:
        return None


class _DocumentCountRepo:
    def __init__(self, *, count: int) -> None:
        self._count = count

    async def count_by_user_id(self, user_id: UUID, **kwargs: object) -> int:
        return self._count


class _BillingRepo:
    def __init__(self, *, subscription: SubscriptionModel | None) -> None:
        self.subscription = subscription
        self.customer: BillingCustomerModel | None = None
        self.recorded_events: list[str] = []

    async def latest_subscription_for_user(self, user_id: UUID) -> SubscriptionModel | None:
        return self.subscription

    async def get_customer_by_user_id(self, user_id: UUID) -> BillingCustomerModel | None:
        return self.customer

    async def get_customer_by_stripe_id(self, stripe_customer_id: str) -> BillingCustomerModel | None:
        if self.customer and self.customer.stripe_customer_id == stripe_customer_id:
            return self.customer
        return None

    async def create_customer(self, *, user_id: UUID, stripe_customer_id: str) -> BillingCustomerModel:
        self.customer = BillingCustomerModel(
            id=uuid4(),
            user_id=user_id,
            stripe_customer_id=stripe_customer_id,
        )
        return self.customer

    async def subscription_by_stripe_id(self, stripe_subscription_id: str) -> SubscriptionModel | None:
        if self.subscription and self.subscription.stripe_subscription_id == stripe_subscription_id:
            return self.subscription
        return None

    async def upsert_subscription(self, **kwargs: object) -> SubscriptionModel:
        self.subscription = _subscription(
            user_id=UUID(str(kwargs["user_id"])),
            plan=str(kwargs["plan"]),
            status=str(kwargs["status"]),
            stripe_customer_id=str(kwargs["stripe_customer_id"]),
            stripe_subscription_id=str(kwargs["stripe_subscription_id"]),
            stripe_price_id=str(kwargs["stripe_price_id"]) if kwargs["stripe_price_id"] else None,
            seats=int(kwargs["seats"]),
            current_period_end=kwargs["current_period_end"] if isinstance(kwargs["current_period_end"], datetime) else None,
            cancel_at_period_end=bool(kwargs["cancel_at_period_end"]),
            subscription_metadata=kwargs["subscription_metadata"]
            if isinstance(kwargs["subscription_metadata"], dict)
            else {},
        )
        return self.subscription

    async def reserve_event(self, *, stripe_event_id: str, event_type: str, event_data: dict[str, object]) -> bool:
        if stripe_event_id in self.recorded_events:
            return False
        self.recorded_events.append(stripe_event_id)
        return True


def _subscription(
    *,
    user_id: UUID,
    plan: str,
    status: str,
    stripe_customer_id: str = "cus_123",
    stripe_subscription_id: str = "sub_123",
    stripe_price_id: str | None = None,
    seats: int = 1,
    current_period_end: datetime | None = None,
    cancel_at_period_end: bool = False,
    subscription_metadata: dict[str, object] | None = None,
) -> SubscriptionModel:
    return SubscriptionModel(
        id=uuid4(),
        user_id=user_id,
        stripe_customer_id=stripe_customer_id,
        stripe_subscription_id=stripe_subscription_id,
        stripe_price_id=stripe_price_id or f"price_{plan}",
        plan=plan,
        status=status,
        seats=seats,
        current_period_end=current_period_end or datetime.now(UTC),
        cancel_at_period_end=cancel_at_period_end,
        subscription_metadata=subscription_metadata or {},
    )
