from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(slots=True)
class TelegramPairingCodeRecord:
    id: UUID
    user_id: UUID
    api_key_id: UUID
    code_hash: str
    expires_at: datetime
    consumed_at: datetime | None
    created_at: datetime
    updated_at: datetime | None = None


@dataclass(slots=True)
class TelegramChatBindingRecord:
    id: UUID
    user_id: UUID
    api_key_id: UUID | None
    chat_id: str
    chat_username: str | None
    chat_title: str | None
    paired_at: datetime
    revoked_at: datetime | None
    created_at: datetime
    updated_at: datetime | None = None


class ITelegramRepository(ABC):
    @abstractmethod
    async def create_pairing_code(self, record: TelegramPairingCodeRecord) -> TelegramPairingCodeRecord: ...

    @abstractmethod
    async def get_pairing_code_by_hash(self, code_hash: str) -> TelegramPairingCodeRecord | None: ...

    @abstractmethod
    async def consume_pairing_code(self, pairing_code_id: UUID, consumed_at: datetime) -> TelegramPairingCodeRecord: ...

    @abstractmethod
    async def list_bindings_by_user_id(self, user_id: UUID) -> list[TelegramChatBindingRecord]: ...

    @abstractmethod
    async def get_active_binding_by_chat_id(self, chat_id: str) -> TelegramChatBindingRecord | None: ...

    @abstractmethod
    async def upsert_binding(
        self,
        *,
        user_id: UUID,
        api_key_id: UUID,
        chat_id: str,
        chat_username: str | None,
        chat_title: str | None,
        paired_at: datetime,
    ) -> TelegramChatBindingRecord: ...

    @abstractmethod
    async def revoke_binding(self, *, user_id: UUID, binding_id: UUID, revoked_at: datetime) -> TelegramChatBindingRecord | None: ...
