from src.application.dtos.query_dtos import QueryDTO
from src.domain.entities.user_entity import UserEntity
from src.presentation.schemas.query import QueryRequest


def to_query_dto(body: QueryRequest, current_user: UserEntity) -> QueryDTO:
    tag_names = tuple(tag.strip().lower() for tag in body.tag_names or [] if tag.strip())
    ai_preferences = _ai_preferences(current_user.preferences)
    retrieval_depth = _retrieval_depth(ai_preferences)
    return QueryDTO(
        user_id=current_user.id,
        query=body.query,
        conversation_id=body.conversation_id,
        collection_id=body.collection_id,
        tag_names=tag_names or None,
        document_types=tuple(body.document_types) if body.document_types else None,
        limit=_query_limit(body.limit, retrieval_depth),
        answer_language=_answer_language(ai_preferences),
        retrieval_depth=retrieval_depth,
    )


def _ai_preferences(preferences: dict[str, object]) -> dict[str, object]:
    ai = preferences.get("ai")
    return ai if isinstance(ai, dict) else {}


def _answer_language(ai_preferences: dict[str, object]) -> str:
    value = ai_preferences.get("answer_language")
    return value if value in {"match_question", "english", "ukrainian"} else "match_question"


def _retrieval_depth(ai_preferences: dict[str, object]) -> str:
    value = ai_preferences.get("retrieval_depth")
    return value if value in {"focused", "balanced", "broad"} else "balanced"


def _query_limit(request_limit: int, retrieval_depth: str) -> int:
    if retrieval_depth == "focused":
        return min(request_limit, 5)
    if retrieval_depth == "broad":
        return max(request_limit, 12)
    return request_limit
