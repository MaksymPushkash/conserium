"""Minimal Telegram-to-Conserium ingestion adapter.

Run separately from the Conserium API:

    CONSERIUM_API_BASE_URL=https://api.conserium.app/api/v1 \
    CONSERIUM_TELEGRAM_SECRET=... \
    TELEGRAM_BOT_TOKEN=... \
    uvicorn scripts.telegram_webhook_bot:app --host 0.0.0.0 --port 8090

Set Telegram webhook to:

    https://<bot-host>/telegram/webhook

Pairing codes are generated in Conserium Settings and consumed when a user sends /pair CODE.
"""

from __future__ import annotations

import os
from typing import Any, cast

import httpx
from fastapi import FastAPI, Header, HTTPException, Request, status

app = FastAPI(title="conserium-telegram-bot")


@app.post("/telegram/webhook")
async def telegram_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
) -> dict[str, str]:
    secret = os.getenv("TELEGRAM_WEBHOOK_SECRET")
    if secret and x_telegram_bot_api_secret_token != secret:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid telegram webhook secret")

    update = await request.json()
    message = update.get("message") or update.get("edited_message") or {}
    chat_id = message.get("chat", {}).get("id")
    message_id = message.get("message_id")
    text = message.get("text") or message.get("caption") or ""
    if not chat_id or not message_id or not text.strip():
        return {"status": "ignored"}
    command = text.strip()
    if command == "/unpair":
        await reply_to_telegram(chat_id=chat_id, text="Conserium: revoke this Telegram chat from Conserium Settings.")
        return {"status": "revoke_in_settings"}
    if command.startswith("/pair "):
        code = command.removeprefix("/pair ").strip()
        paired = await consume_pairing_code(code=code, message=message)
        if not paired:
            await reply_to_telegram(chat_id=chat_id, text="Conserium: invalid or expired pairing code.")
            return {"status": "rejected"}
        await reply_to_telegram(chat_id=chat_id, text="Conserium: Telegram chat paired.")
        return {"status": "paired"}

    payload = telegram_payload(message=message, text=text)
    try:
        result = await send_to_conserium(payload)
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == status.HTTP_404_NOT_FOUND:
            await reply_to_telegram(chat_id=chat_id, text="Conserium: create a Telegram pairing code in Settings, then send /pair CODE.")
            return {"status": "unpaired"}
        raise
    await reply_to_telegram(chat_id=chat_id, text=reply_text(result))
    return {"status": "accepted"}


def telegram_payload(*, message: dict[str, Any], text: str) -> dict[str, Any]:
    link = first_url(message) or (text.strip() if text.strip().startswith(("http://", "https://")) else None)
    chat_id = message.get("chat", {}).get("id")
    message_id = message.get("message_id")
    if link:
        doc_type = "YOUTUBE" if "youtube.com/watch" in link or "youtu.be/" in link else "URL"
        return {
            "title": link,
            "type": doc_type,
            "chat_id": str(chat_id),
            "source_url": link,
            "provider": "telegram",
            "external_id": f"{chat_id}:{message_id}",
            "idempotency_key": f"telegram:{chat_id}:{message_id}",
            "metadata": {"telegram_chat_id": chat_id, "telegram_message_id": message_id},
        }
    return {
        "title": text.strip()[:120],
        "type": "TEXT",
        "chat_id": str(chat_id),
        "raw_content": text,
        "provider": "telegram",
        "external_id": f"{chat_id}:{message_id}",
        "idempotency_key": f"telegram:{chat_id}:{message_id}",
        "metadata": {"telegram_chat_id": chat_id, "telegram_message_id": message_id},
    }


def first_url(message: dict[str, Any]) -> str | None:
    text = message.get("text") or message.get("caption") or ""
    entities = message.get("entities") or message.get("caption_entities") or []
    for entity in entities:
        if entity.get("type") == "url":
            offset = int(entity.get("offset", 0))
            length = int(entity.get("length", 0))
            return text[offset : offset + length]
        if entity.get("type") == "text_link" and entity.get("url"):
            return str(entity["url"])
    return None


async def consume_pairing_code(*, code: str, message: dict[str, Any]) -> bool:
    api_base = os.environ["CONSERIUM_API_BASE_URL"].rstrip("/")
    chat = message.get("chat", {})
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.post(
            f"{api_base}/integrations/telegram/bot/consume-pairing",
            headers={"X-Conserium-Telegram-Secret": os.environ["CONSERIUM_TELEGRAM_SECRET"]},
            json={
                "code": code,
                "chat_id": str(chat.get("id")),
                "chat_username": chat.get("username"),
                "chat_title": chat.get("title") or chat.get("first_name"),
            },
        )
    return response.status_code < 400


async def send_to_conserium(payload: dict[str, Any]) -> dict[str, Any]:
    api_base = os.environ["CONSERIUM_API_BASE_URL"].rstrip("/")
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.post(
            f"{api_base}/integrations/telegram/bot/ingest",
            headers={"X-Conserium-Telegram-Secret": os.environ["CONSERIUM_TELEGRAM_SECRET"]},
            json=payload,
        )
    response.raise_for_status()
    return cast("dict[str, Any]", response.json())


async def reply_to_telegram(*, chat_id: int, text: str) -> None:
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        return
    async with httpx.AsyncClient(timeout=10) as client:
        await client.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": text},
        )


def reply_text(result: dict[str, Any]) -> str:
    item = result.get("intake_item") or {}
    title = item.get("title") or "item"
    status_value = item.get("status") or "queued"
    return f"Conserium: {title} is {str(status_value).lower()}."
