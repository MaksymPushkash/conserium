"""Minimal Telegram-to-Cortex ingestion adapter.

Run separately from the Cortex API:

    CORTEX_API_BASE_URL=https://api.cortexx.me/api/v1 \
    CORTEX_API_KEY=ctx_... \
    TELEGRAM_BOT_TOKEN=... \
    uvicorn scripts.telegram_webhook_bot:app --host 0.0.0.0 --port 8090

Set Telegram webhook to:

    https://<bot-host>/telegram/webhook
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, cast

import httpx
from fastapi import FastAPI, Header, HTTPException, Request, status

app = FastAPI(title="cortex-telegram-bot")


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
    if text.strip().startswith("/pair "):
        api_key = text.strip().removeprefix("/pair ").strip()
        if not api_key.startswith("ctx_"):
            await reply_to_telegram(chat_id=chat_id, text="Cortex: invalid API key.")
            return {"status": "rejected"}
        save_chat_api_key(chat_id=chat_id, api_key=api_key)
        await reply_to_telegram(chat_id=chat_id, text="Cortex: Telegram chat paired.")
        return {"status": "paired"}

    payload = telegram_payload(message=message, text=text)
    api_key = api_key_for_chat(chat_id)
    if api_key is None:
        await reply_to_telegram(chat_id=chat_id, text="Cortex: send /pair ctx_... before forwarding items.")
        return {"status": "unpaired"}
    result = await send_to_cortex(payload, api_key=api_key)
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
            "source_url": link,
            "provider": "telegram",
            "external_id": f"{chat_id}:{message_id}",
            "idempotency_key": f"telegram:{chat_id}:{message_id}",
            "metadata": {"telegram_chat_id": chat_id, "telegram_message_id": message_id},
        }
    return {
        "title": text.strip()[:120],
        "type": "TEXT",
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


async def send_to_cortex(payload: dict[str, Any], *, api_key: str) -> dict[str, Any]:
    api_base = os.environ["CORTEX_API_BASE_URL"].rstrip("/")
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.post(
            f"{api_base}/webhooks/ingest",
            headers={"Authorization": f"Bearer {api_key}"},
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
    return f"Cortex: {title} is {str(status_value).lower()}."


def api_key_for_chat(chat_id: int) -> str | None:
    pairings = load_pairings()
    value = pairings.get(str(chat_id)) or os.getenv("CORTEX_API_KEY")
    return value if value and value.startswith("ctx_") else None


def save_chat_api_key(*, chat_id: int, api_key: str) -> None:
    pairings = load_pairings()
    pairings[str(chat_id)] = api_key
    pairings_path().write_text(json.dumps(pairings, indent=2, sort_keys=True), encoding="utf-8")


def load_pairings() -> dict[str, str]:
    path = pairings_path()
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        return {}
    return {str(key): str(value) for key, value in data.items()}


def pairings_path() -> Path:
    return Path(os.getenv("CORTEX_TELEGRAM_PAIRINGS_FILE", ".cortex_telegram_pairings.json"))
