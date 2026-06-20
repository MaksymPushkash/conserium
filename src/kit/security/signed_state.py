import base64
import hashlib
import hmac
import json
import time
from typing import Any

from src.kit.exceptions import InvalidTokenException


class SignedState:
    def __init__(self, secret: str, ttl_seconds: int = 300) -> None:
        self._secret = secret.encode("utf-8")
        self._ttl_seconds = ttl_seconds

    def sign(self, payload: dict[str, Any]) -> str:
        expires_at = int(time.time()) + self._ttl_seconds
        body = base64.urlsafe_b64encode(json.dumps({**payload, "exp": expires_at}, separators=(",", ":")).encode("utf-8")).decode("utf-8")
        signature = self._signature(body)
        return f"{body}.{signature}"

    def verify(self, value: str) -> dict[str, Any]:
        body, separator, signature = value.partition(".")
        if not separator or not hmac.compare_digest(signature, self._signature(body)):
            raise InvalidTokenException("invalid state")
        payload = json.loads(base64.urlsafe_b64decode(body.encode("utf-8")).decode("utf-8"))
        if not isinstance(payload, dict):
            raise InvalidTokenException("invalid state")
        if int(payload.get("exp", 0)) < int(time.time()):
            raise InvalidTokenException("expired state")
        return payload

    def _signature(self, body: str) -> str:
        digest = hmac.new(self._secret, body.encode("utf-8"), hashlib.sha256).digest()
        return base64.urlsafe_b64encode(digest).decode("utf-8")
