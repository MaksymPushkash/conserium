from __future__ import annotations

import json
from typing import Any, cast

import stripe

from src.kit.exceptions import ValidationException
from src.settings import settings


def parse_stripe_event(body: bytes, stripe_signature: str | None) -> dict[str, Any]:
    if settings.STRIPE_WEBHOOK_SECRET:
        if not stripe_signature:
            raise ValidationException("Missing Stripe signature")
            
        construct_event = cast("Any", stripe.Webhook.construct_event)
        return cast("dict[str, Any]", construct_event(body, stripe_signature, settings.STRIPE_WEBHOOK_SECRET))
        
    if not settings.DEBUG:
        raise ValidationException("Stripe webhook secret is not configured")
        
    return cast("dict[str, Any]", json.loads(body.decode("utf-8")))


__all__ = ["parse_stripe_event"]
