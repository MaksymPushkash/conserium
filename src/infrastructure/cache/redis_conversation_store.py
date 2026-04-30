import json
from datetime import datetime
from uuid import UUID

from src.application.dtos.conversation_dtos import ConversationSourceDTO, ConversationTurnDTO
from src.application.ports.cache.cache import ICache
from src.application.ports.conversations.conversation_store import IConversationStore


class RedisConversationStore(IConversationStore):
    MAX_STORED_TURNS = 50

    def __init__(self, cache: ICache) -> None:
        self._cache = cache

    async def get_recent_turns(
        self,
        *,
        user_id: UUID,
        conversation_id: UUID,
        limit: int,
    ) -> list[ConversationTurnDTO]:
        raw_value = await self._cache.get(_conversation_key(user_id, conversation_id))
        if raw_value is None:
            return []
        try:
            payload = json.loads(raw_value)
        except json.JSONDecodeError:
            return []
        if not isinstance(payload, list):
            return []
        turns = [_turn_from_payload(item) for item in payload if isinstance(item, dict)]
        return turns[-limit:]

    async def append_turn(
        self,
        *,
        user_id: UUID,
        conversation_id: UUID,
        turn: ConversationTurnDTO,
        ttl_seconds: int,
    ) -> None:
        turns = await self.get_recent_turns(
            user_id=user_id,
            conversation_id=conversation_id,
            limit=self.MAX_STORED_TURNS,
        )
        turns.append(turn)
        stored_turns = turns[-self.MAX_STORED_TURNS :]
        await self._cache.set(
            _conversation_key(user_id, conversation_id),
            json.dumps([_turn_to_payload(item) for item in stored_turns], separators=(",", ":")),
            ttl_seconds,
        )


def _conversation_key(user_id: UUID, conversation_id: UUID) -> str:
    return f"conversation:{user_id}:{conversation_id}"


def _turn_to_payload(turn: ConversationTurnDTO) -> dict[str, object]:
    return {
        "query": turn.query,
        "answer": turn.answer,
        "sources": [
            {
                "chunk_id": str(source.chunk_id),
                "document_id": str(source.document_id),
                "document_title": source.document_title,
                "page_number": source.page_number,
                "chunk_index": source.chunk_index,
                "score": source.score,
            }
            for source in turn.sources
        ],
        "created_at": turn.created_at.isoformat(),
    }


def _turn_from_payload(payload: dict[str, object]) -> ConversationTurnDTO:
    raw_sources = payload.get("sources", [])
    sources = []
    if isinstance(raw_sources, list):
        sources = [_source_from_payload(source) for source in raw_sources if isinstance(source, dict)]
    return ConversationTurnDTO(
        query=str(payload.get("query", "")),
        answer=str(payload.get("answer", "")),
        sources=sources,
        created_at=datetime.fromisoformat(str(payload["created_at"])),
    )


def _source_from_payload(payload: dict[str, object]) -> ConversationSourceDTO:
    return ConversationSourceDTO(
        chunk_id=UUID(str(payload["chunk_id"])),
        document_id=UUID(str(payload["document_id"])),
        document_title=str(payload["document_title"]) if payload.get("document_title") is not None else None,
        page_number=int(str(payload["page_number"])) if payload.get("page_number") is not None else None,
        chunk_index=int(str(payload["chunk_index"])),
        score=float(str(payload["score"])) if payload.get("score") is not None else None,
    )
