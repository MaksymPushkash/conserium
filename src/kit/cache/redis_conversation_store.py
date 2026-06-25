import asyncio
import json
import uuid
from datetime import datetime
from uuid import UUID

from src.kit.cache.redis_cache import RedisCache
from src.query.schemas import ConversationSource, ConversationTurn


class RedisConversationStore:
    MAX_STORED_TURNS = 50
    _LOCK_TTL_SECONDS = 10
    _LOCK_RETRY_DELAY_SECONDS = 0.01
    _LOCK_RETRY_LIMIT = 200

    def __init__(self, cache: RedisCache) -> None:
        self._cache = cache

    async def get_recent_turns(
        self,
        *,
        user_id: UUID,
        conversation_id: UUID,
        limit: int,
    ) -> list[ConversationTurn]:
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
        turn: ConversationTurn,
        ttl_seconds: int,
    ) -> None:
        turns = await self.get_recent_turns(
            user_id=user_id,
            conversation_id=conversation_id,
            limit=self.MAX_STORED_TURNS,
        )
        lock_key = f"{_conversation_key(user_id, conversation_id)}:lock"
        lock_token = str(uuid.uuid4())
        await _acquire_lock(self._cache, lock_key=lock_key, lock_token=lock_token)
        try:
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
        finally:
            current_lock = await self._cache.get(lock_key)
            if current_lock == lock_token:
                await self._cache.delete(lock_key)


def _conversation_key(user_id: UUID, conversation_id: UUID) -> str:
    return f"conversation:{user_id}:{conversation_id}"


def _turn_to_payload(turn: ConversationTurn) -> dict[str, object]:
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


def _turn_from_payload(payload: dict[str, object]) -> ConversationTurn:
    raw_sources = payload.get("sources", [])
    sources = []
    if isinstance(raw_sources, list):
        sources = [_source_from_payload(source) for source in raw_sources if isinstance(source, dict)]
    return ConversationTurn(
        query=str(payload.get("query", "")),
        answer=str(payload.get("answer", "")),
        sources=sources,
        created_at=datetime.fromisoformat(str(payload["created_at"])),
    )


def _source_from_payload(payload: dict[str, object]) -> ConversationSource:
    return ConversationSource(
        chunk_id=UUID(str(payload["chunk_id"])),
        document_id=UUID(str(payload["document_id"])),
        document_title=str(payload["document_title"]) if payload.get("document_title") is not None else None,
        page_number=int(str(payload["page_number"])) if payload.get("page_number") is not None else None,
        chunk_index=int(str(payload["chunk_index"])),
        score=float(str(payload["score"])) if payload.get("score") is not None else None,
    )


async def _acquire_lock(cache: RedisCache, *, lock_key: str, lock_token: str) -> None:
    for _attempt in range(RedisConversationStore._LOCK_RETRY_LIMIT):
        acquired = await cache.set_if_absent(lock_key, lock_token, RedisConversationStore._LOCK_TTL_SECONDS)
        if acquired:
            return
        await asyncio.sleep(RedisConversationStore._LOCK_RETRY_DELAY_SECONDS)
    raise RuntimeError("conversation store lock acquisition timed out")
