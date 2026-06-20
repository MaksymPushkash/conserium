from uuid import UUID

from src.query.agents.state import ConseriumQueryState
from src.query.schemas import ConversationTurnDTO

_FOLLOW_UP_EXACT_MARKERS = frozenset(
    {
        "it",
        "its",
        "that",
        "this",
        "they",
        "them",
        "those",
        "there",
        "he",
        "she",
        "same",
        "more",
        "another",
        "його",
        "її",
        "це",
        "цей",
        "ця",
        "вони",
        "також",
    }
)
_FOLLOW_UP_PREFIX_MARKERS = frozenset(
    {
        "it",
        "its",
        "that",
        "this",
        "they",
        "them",
        "those",
        "there",
        "he",
        "she",
        "what about",
        "how about",
        "and",
        "also",
        "same",
        "more",
        "another",
        "його",
        "її",
        "це",
        "цей",
        "ця",
        "вони",
        "також",
    }
)


class ConversationContextAgent:
    RECENT_CONTEXT_LIMIT = 3

    def apply(self, state: ConseriumQueryState) -> ConseriumQueryState:
        state.promoted_document_ids = []
        if state.retrieval_query:
            return state
        if not state.conversation_turns:
            state.retrieval_query = state.query
            return state

        if not _looks_like_follow_up(state.query):
            state.retrieval_query = state.query
            return state

        recent_turns = state.conversation_turns[-self.RECENT_CONTEXT_LIMIT :]
        state.promoted_document_ids = _recent_document_ids(recent_turns)
        state.retrieval_query = _build_contextual_query(state.query, recent_turns)
        return state


def _looks_like_follow_up(query: str) -> bool:
    normalized_query = query.casefold().strip()
    if normalized_query in _FOLLOW_UP_EXACT_MARKERS:
        return True
    return any(normalized_query.startswith(f"{marker} ") for marker in _FOLLOW_UP_PREFIX_MARKERS)


def _build_contextual_query(query: str, turns: list[ConversationTurnDTO]) -> str:
    context_parts = []
    for turn in turns:
        titles = sorted({source.document_title for source in turn.sources if source.document_title})
        source_text = f" Sources: {', '.join(titles)}." if titles else ""
        context_parts.append(f"Previous question: {turn.query}. Previous answer: {turn.answer}.{source_text}")
    return f"Current follow-up question: {query}\n" + "\n".join(context_parts)


def _recent_document_ids(turns: list[ConversationTurnDTO]) -> list[UUID]:
    seen: set[UUID] = set()
    document_ids: list[UUID] = []
    for turn in reversed(turns):
        for source in turn.sources:
            if source.document_id not in seen:
                seen.add(source.document_id)
                document_ids.append(source.document_id)
    return document_ids
