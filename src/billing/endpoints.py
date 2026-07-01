from fastapi import Depends, Header, Request, status

from src.auth.auth import CurrentUser
from src.billing.schemas import (
    BillingCheckoutRequest,
    BillingCheckoutResponse,
    BillingPortalRequest,
    BillingPortalResponse,
    BillingSubscriptionResponse,
)
from src.billing.service import billing
from src.postgres import AsyncReadSession, AsyncSession, get_db_read_session, get_db_session
from src.routing import APIRouter

router = APIRouter(prefix="/billing", tags=["billing"])


@router.get("/subscription", response_model=BillingSubscriptionResponse)
async def get_subscription(
    current_user: CurrentUser,
    session: AsyncReadSession = Depends(get_db_read_session),
) -> BillingSubscriptionResponse:
    return await billing.subscription(session, user_id=current_user.id)


@router.post("/checkout", response_model=BillingCheckoutResponse)
async def create_checkout(
    body: BillingCheckoutRequest,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_db_session),
) -> BillingCheckoutResponse:
    return await billing.create_checkout(session, user_id=current_user.id, email=current_user.email, body=body)


@router.post("/portal", response_model=BillingPortalResponse)
async def create_portal(
    body: BillingPortalRequest,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_db_session),
) -> BillingPortalResponse:
    return await billing.create_portal(session, user_id=current_user.id, email=current_user.email, body=body)


@router.post("/webhook", status_code=status.HTTP_200_OK)
async def stripe_webhook(
    request: Request,
    stripe_signature: str | None = Header(default=None, alias="Stripe-Signature"),
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, bool]:
    body = await request.body()
    await billing.handle_webhook(session, body=body, stripe_signature=stripe_signature)
    return {"received": True}
