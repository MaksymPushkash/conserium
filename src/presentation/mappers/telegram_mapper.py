from src.application.dtos.telegram_dtos import TelegramChatBindingDTO, TelegramPairingCodeDTO, TelegramStatusDTO
from src.presentation.schemas.telegram import (
    TelegramChatBindingResponse,
    TelegramPairingCodeResponse,
    TelegramStatusResponse,
)


def to_telegram_pairing_code_response(dto: TelegramPairingCodeDTO) -> TelegramPairingCodeResponse:
    return TelegramPairingCodeResponse(id=dto.id, code=dto.code, expires_at=dto.expires_at)


def to_telegram_binding_response(dto: TelegramChatBindingDTO) -> TelegramChatBindingResponse:
    return TelegramChatBindingResponse(
        id=dto.id,
        chat_id=dto.chat_id,
        chat_username=dto.chat_username,
        chat_title=dto.chat_title,
        paired_at=dto.paired_at,
        revoked_at=dto.revoked_at,
        created_at=dto.created_at,
        updated_at=dto.updated_at,
    )


def to_telegram_status_response(dto: TelegramStatusDTO) -> TelegramStatusResponse:
    return TelegramStatusResponse(bindings=[to_telegram_binding_response(binding) for binding in dto.bindings])
