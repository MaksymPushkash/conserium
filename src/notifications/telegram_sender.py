from __future__ import annotations

import httpx

from src.kit.ports.notifications import INotificationSender, NotificationDeliveryUnavailable
from src.settings import settings


class TelegramNotificationSender(INotificationSender):
    async def send_telegram(self, *, chat_id: str, subject: str, body: str) -> None:
        if not settings.TELEGRAM_BOT_TOKEN:
            raise NotificationDeliveryUnavailable("TELEGRAM_BOT_TOKEN is not configured")
        text = f"{subject}\n\n{body}"[:3900]
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/sendMessage",
                json={"chat_id": chat_id, "text": text, "disable_web_page_preview": True},
            )
            response.raise_for_status()
