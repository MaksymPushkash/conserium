from __future__ import annotations

from abc import ABC, abstractmethod


class NotificationDeliveryUnavailable(Exception):
    pass


class INotificationSender(ABC):
    @abstractmethod
    async def send_telegram(self, *, chat_id: str, subject: str, body: str) -> None: ...
