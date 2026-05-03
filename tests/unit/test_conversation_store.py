import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, cast

from src.application.dtos.conversation_dtos import ConversationSourceDTO, ConversationTurnDTO
from src.infrastructure.cache.redis_conversation_store import RedisConversationStore

if TYPE_CHECKING:
    from src.application.ports.cache.cache import ICache


class _FakeCache:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.ttls: dict[str, int] = {}

    async def get(self, key: str) -> str | None:
        return self.values.get(key)

    async def get_del(self, key: str) -> str | None:
        return self.values.pop(key, None)

    async def set(self, key: str, value: str, ttl: int) -> None:
        self.values[key] = value
        self.ttls[key] = ttl

    async def set_if_absent(self, key: str, value: str, ttl: int) -> bool:
        if key in self.values:
            return False
        self.values[key] = value
        self.ttls[key] = ttl
        return True

    async def delete(self, key: str) -> None:
        self.values.pop(key, None)

    async def exists(self, key: str) -> bool:
        return key in self.values


async def test_redis_conversation_store_appends_and_reads_recent_turns() -> None:
    cache = _FakeCache()
    store = RedisConversationStore(cast("ICache", cache))
    user_id = uuid.uuid4()
    conversation_id = uuid.uuid4()
    source = ConversationSourceDTO(
        chunk_id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        document_title="Architecture Notes",
        page_number=12,
        chunk_index=0,
        score=0.75,
    )

    await store.append_turn(
        user_id=user_id,
        conversation_id=conversation_id,
        turn=ConversationTurnDTO(
            query="What did I read?",
            answer="You read about dependency direction.",
            sources=[source],
            created_at=datetime.now(UTC),
        ),
        ttl_seconds=60,
    )

    turns = await store.get_recent_turns(user_id=user_id, conversation_id=conversation_id, limit=5)

    assert len(turns) == 1
    assert turns[0].query == "What did I read?"
    assert turns[0].sources[0].document_title == "Architecture Notes"
    assert cache.ttls[f"conversation:{user_id}:{conversation_id}"] == 60
