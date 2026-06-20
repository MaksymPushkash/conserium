from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Self
from uuid import UUID

from sqlalchemy import delete, func, select

from src.chats.schemas import ChatDetailDTO, ChatMessageDTO, ChatSessionDTO, ChatSessionListDTO, JsonObject
from src.models.chat import ChatMessageModel, ChatSessionModel
from src.query.schemas import ConversationSourceDTO, ConversationTurnDTO

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


class ChatRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @classmethod
    def from_session(cls, session: AsyncSession) -> Self:
        return cls(session)

    async def create_session(
        self,
        *,
        user_id: UUID,
        title: str,
        chat_id: UUID | None = None,
    ) -> ChatSessionDTO:
        if chat_id is None:
            model = ChatSessionModel(user_id=user_id, title=title, message_count=0)
        else:
            model = ChatSessionModel(id=chat_id, user_id=user_id, title=title, message_count=0)
        self._session.add(model)
        await self._session.flush()
        return _session_to_dto(model)

    async def get_session(self, *, user_id: UUID, chat_id: UUID) -> ChatSessionDTO | None:
        model = await self._get_session_model(user_id=user_id, chat_id=chat_id)
        return _session_to_dto(model) if model is not None else None

    async def list_sessions(self, *, user_id: UUID, limit: int, offset: int) -> ChatSessionListDTO:
        items_result = await self._session.execute(
            select(ChatSessionModel)
            .where(ChatSessionModel.user_id == user_id)
            .order_by(
                func.coalesce(ChatSessionModel.updated_at, ChatSessionModel.created_at).desc(),
                ChatSessionModel.created_at.desc(),
            )
            .limit(limit)
            .offset(offset)
        )
        count_result = await self._session.execute(
            select(func.count()).select_from(ChatSessionModel).where(ChatSessionModel.user_id == user_id)
        )
        return ChatSessionListDTO(
            items=[_session_to_dto(model) for model in items_result.scalars().all()],
            total=count_result.scalar_one(),
            limit=limit,
            offset=offset,
        )

    async def get_detail(self, *, user_id: UUID, chat_id: UUID, message_limit: int) -> ChatDetailDTO | None:
        session_model = await self._get_session_model(user_id=user_id, chat_id=chat_id)
        if session_model is None:
            return None
        messages_result = await self._session.execute(
            select(ChatMessageModel).where(ChatMessageModel.chat_id == chat_id).order_by(ChatMessageModel.created_at.asc()).limit(message_limit)
        )
        return ChatDetailDTO(
            session=_session_to_dto(session_model),
            messages=[_message_to_dto(model) for model in messages_result.scalars().all()],
        )

    async def rename_session(self, *, user_id: UUID, chat_id: UUID, title: str) -> ChatSessionDTO | None:
        model = await self._get_session_model(user_id=user_id, chat_id=chat_id)
        if model is None:
            return None
        model.title = title
        model.updated_at = datetime.now(UTC)
        await self._session.flush()
        return _session_to_dto(model)

    async def delete_session(self, *, user_id: UUID, chat_id: UUID) -> None:
        await self._session.execute(delete(ChatSessionModel).where(ChatSessionModel.user_id == user_id, ChatSessionModel.id == chat_id))

    async def append_message(
        self,
        *,
        chat_id: UUID,
        role: str,
        content: str,
        sources: list[JsonObject] | None = None,
        refrag_context: JsonObject | None = None,
        eval_scores: JsonObject | None = None,
        trace_id: str | None = None,
    ) -> ChatMessageDTO:
        message = ChatMessageModel(
            chat_id=chat_id,
            role=role,
            content=content,
            sources=sources,
            refrag_context=refrag_context,
            eval_scores=eval_scores,
            trace_id=trace_id,
        )
        self._session.add(message)
        session_model = await self._session.get(ChatSessionModel, chat_id)
        if session_model is not None:
            session_model.message_count += 1
            session_model.updated_at = datetime.now(UTC)
        await self._session.flush()
        return _message_to_dto(message)

    async def get_recent_turns(self, *, user_id: UUID, chat_id: UUID, limit: int) -> list[ConversationTurnDTO]:
        session_model = await self._get_session_model(user_id=user_id, chat_id=chat_id)
        if session_model is None:
            return []
        result = await self._session.execute(
            select(ChatMessageModel).where(ChatMessageModel.chat_id == chat_id).order_by(ChatMessageModel.created_at.desc()).limit(limit * 2 + 2)
        )
        messages = list(reversed(result.scalars().all()))
        turns: list[ConversationTurnDTO] = []
        pending_query: ChatMessageModel | None = None
        for message in messages:
            if message.role == "user":
                pending_query = message
                continue
            if message.role == "assistant" and pending_query is not None:
                turns.append(
                    ConversationTurnDTO(
                        query=pending_query.content,
                        answer=message.content,
                        sources=_conversation_sources(message.sources),
                        created_at=message.created_at,
                    )
                )
                pending_query = None
        return turns[-limit:]

    async def _get_session_model(self, *, user_id: UUID, chat_id: UUID) -> ChatSessionModel | None:
        result = await self._session.execute(
            select(ChatSessionModel).where(ChatSessionModel.user_id == user_id, ChatSessionModel.id == chat_id)
        )
        return result.scalar_one_or_none()


def _session_to_dto(model: ChatSessionModel) -> ChatSessionDTO:
    return ChatSessionDTO(
        id=model.id,
        user_id=model.user_id,
        title=model.title,
        message_count=model.message_count,
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


def _message_to_dto(model: ChatMessageModel) -> ChatMessageDTO:
    return ChatMessageDTO(
        id=model.id,
        chat_id=model.chat_id,
        role=model.role,
        content=model.content,
        sources=model.sources,
        refrag_context=model.refrag_context,
        eval_scores=model.eval_scores,
        trace_id=model.trace_id,
        created_at=model.created_at,
    )


def _conversation_sources(sources: list[JsonObject] | None) -> list[ConversationSourceDTO]:
    if not sources:
        return []
    result: list[ConversationSourceDTO] = []
    for source in sources:
        try:
            result.append(
                ConversationSourceDTO(
                    chunk_id=UUID(str(source["chunk_id"])),
                    document_id=UUID(str(source["document_id"])),
                    document_title=str(source["document_title"]) if source.get("document_title") is not None else None,
                    page_number=int(str(source["page_number"])) if source.get("page_number") is not None else None,
                    chunk_index=int(str(source["chunk_index"])),
                    score=float(str(source["score"])) if source.get("score") is not None else None,
                )
            )
        except (KeyError, TypeError, ValueError):
            continue
    return result


__all__ = ["ChatRepository"]
