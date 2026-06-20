from typing import Any

import httpx
import pytest

from src.integrations.notion_export_client import NotionExportClient
from src.integrations.notion_oauth_client import NotionOAuthClient
from src.kit.exceptions import IntegrationRequestException


class _RejectedResponse:
    def raise_for_status(self) -> None:
        request = httpx.Request("POST", "https://api.notion.com/v1/pages")
        response = httpx.Response(403, request=request)
        raise httpx.HTTPStatusError("forbidden", request=request, response=response)

    def json(self) -> dict[str, Any]:
        return {}


class _RejectingAsyncClient:
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        pass

    async def __aenter__(self) -> "_RejectingAsyncClient":
        return self

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None

    async def post(self, *args: Any, **kwargs: Any) -> _RejectedResponse:
        return _RejectedResponse()


class _UnavailableAsyncClient:
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        pass

    async def __aenter__(self) -> "_UnavailableAsyncClient":
        return self

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None

    async def post(self, *args: Any, **kwargs: Any) -> _RejectedResponse:
        raise httpx.ConnectError("connection failed")


@pytest.mark.asyncio
async def test_notion_export_client_maps_http_status_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("src.integrations.notion_export_client.httpx.AsyncClient", _RejectingAsyncClient)
    client = NotionExportClient(token="token", parent_page_id="parent-page-id")

    with pytest.raises(IntegrationRequestException, match="notion rejected the export request"):
        await client.create_markdown_page(title="Draft", markdown="# Draft")


@pytest.mark.asyncio
async def test_notion_export_client_maps_transport_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("src.integrations.notion_export_client.httpx.AsyncClient", _UnavailableAsyncClient)
    client = NotionExportClient(token="token", parent_page_id="parent-page-id")

    with pytest.raises(IntegrationRequestException, match="notion export request failed"):
        await client.create_markdown_page(title="Draft", markdown="# Draft")


@pytest.mark.asyncio
async def test_notion_oauth_client_maps_http_status_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("src.integrations.notion_oauth_client.httpx.AsyncClient", _RejectingAsyncClient)
    client = NotionOAuthClient(client_id="client-id", client_secret="client-secret")

    with pytest.raises(IntegrationRequestException, match="notion rejected the oauth callback"):
        await client.exchange_code(code="code", redirect_uri="https://app.test/callback")


@pytest.mark.asyncio
async def test_notion_oauth_client_maps_transport_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("src.integrations.notion_oauth_client.httpx.AsyncClient", _UnavailableAsyncClient)
    client = NotionOAuthClient(client_id="client-id", client_secret="client-secret")

    with pytest.raises(IntegrationRequestException, match="notion oauth request failed"):
        await client.exchange_code(code="code", redirect_uri="https://app.test/callback")
