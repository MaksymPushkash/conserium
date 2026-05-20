import base64
from typing import Any
from urllib.parse import urlencode

import httpx

from src.application.ports.integrations.notion_oauth_client import INotionOAuthClient, NotionOAuthToken
from src.core.config import settings
from src.domain.exceptions import IntegrationConfigurationException, IntegrationRequestException

_NOTION_OAUTH_AUTHORIZE_URL = "https://api.notion.com/v1/oauth/authorize"
_NOTION_OAUTH_TOKEN_URL = "https://api.notion.com/v1/oauth/token"


class NotionOAuthClient(INotionOAuthClient):
    def __init__(self, client_id: str | None = None, client_secret: str | None = None) -> None:
        self._client_id = client_id if client_id is not None else settings.NOTION_CLIENT_ID
        self._client_secret = client_secret if client_secret is not None else settings.NOTION_CLIENT_SECRET

    def authorization_url(self, *, redirect_uri: str, state: str) -> str:
        if not self._client_id or not self._client_secret:
            raise IntegrationConfigurationException("notion oauth is not configured")
        return f"{_NOTION_OAUTH_AUTHORIZE_URL}?{urlencode({'client_id': self._client_id, 'response_type': 'code', 'owner': 'user', 'redirect_uri': redirect_uri, 'state': state})}"

    async def exchange_code(self, *, code: str, redirect_uri: str) -> NotionOAuthToken:
        if not self._client_id or not self._client_secret:
            raise IntegrationConfigurationException("notion oauth is not configured")

        credentials = base64.b64encode(f"{self._client_id}:{self._client_secret}".encode()).decode("utf-8")
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                response = await client.post(
                    _NOTION_OAUTH_TOKEN_URL,
                    headers={
                        "Authorization": f"Basic {credentials}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "grant_type": "authorization_code",
                        "code": code,
                        "redirect_uri": redirect_uri,
                    },
                )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise IntegrationRequestException("notion rejected the oauth callback") from exc
        except httpx.HTTPError as exc:
            raise IntegrationRequestException("notion oauth request failed") from exc
        payload: dict[str, Any] = response.json()
        access_token = payload.get("access_token")
        if not isinstance(access_token, str) or not access_token:
            raise IntegrationRequestException("notion oauth did not return an access token")
        owner = payload.get("owner")
        return NotionOAuthToken(
            access_token=access_token,
            workspace_id=payload.get("workspace_id") if isinstance(payload.get("workspace_id"), str) else None,
            workspace_name=payload.get("workspace_name") if isinstance(payload.get("workspace_name"), str) else None,
            bot_id=payload.get("bot_id") if isinstance(payload.get("bot_id"), str) else None,
            owner=owner if isinstance(owner, dict) else None,
        )
