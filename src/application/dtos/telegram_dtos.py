from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True, slots=True)
class TelegramPairingCodeDTO:
    id: UUID
    code: str
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class TelegramChatBindingDTO:
    id: UUID
    user_id: UUID
    api_key_id: UUID | None
    chat_id: str
    chat_username: str | None
    chat_title: str | None
    paired_at: datetime
    revoked_at: datetime | None
    created_at: datetime
    updated_at: datetime | None


@dataclass(frozen=True, slots=True)
class TelegramStatusDTO:
    bindings: list[TelegramChatBindingDTO]
