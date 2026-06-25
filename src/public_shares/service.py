import logging
import secrets
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy.ext.asyncio import async_sessionmaker

from src.kit.exceptions import ApplicationStateException, ResourceNotFoundException, ValidationException
from src.postgres import AsyncSession
from src.public_shares.repository import AnswerShareRepository, CollectionShareRepository
from src.public_shares.schemas import (
    AnswerShareListResponse,
    AnswerShareRecord,
    AnswerShareResponse,
    AnswerShareSource,
    AnswerShareSourceResponse,
    CollectionShareRecord,
    PublicAnswerShareResponse,
    PublicAnswerShareSourceResponse,
    PublicCollectionDocument,
    PublicCollectionDocumentResponse,
    PublicCollectionResponse,
    PublicCollectionResult,
)
from src.query.agents.graph_runner import QueryGraphRunner
from src.query.agents.state import ConseriumQueryState
from src.query.schemas import PublicCollectionQueryResponse, PublicQuerySourceResponse, QueryResult, QuerySource
from src.query.services.query.payloads import build_follow_up_questions, mark_sources_used_in_answer, query_debug

_PUBLIC_COLLECTION_OWNER_DAILY_CAP = 500
logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class PublicCollectionQueryResult:
    result: QueryResult
    share: AnswerShareRecord


@dataclass(frozen=True, slots=True)
class PublicAskReservation:
    id: UUID
    share: CollectionShareRecord


class PublicAskLedger:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def reserve(self, *, slug: str, query: str, client_key: str) -> PublicAskReservation:
        since = datetime.now(UTC) - timedelta(days=1)
        async with self._session_factory() as session:
            repository = CollectionShareRepository.from_session(session)
            share = await repository.get_active_by_slug(slug)
            if share is None:
                raise ResourceNotFoundException("public collection not found")
            if not share.ask_enabled:
                await _record_public_ask_event(repository, share, client_key, query, "blocked", "disabled")
                await session.commit()
                raise ValidationException("public Ask is disabled for this collection")

            share = await repository.lock_public_ask_scope(owner_user_id=share.user_id, share_slug=slug)
            if share is None:
                raise ResourceNotFoundException("public collection not found")

            share_count = await repository.count_public_ask_events_by_share(share_slug=slug, since=since)
            owner_count = await repository.count_public_ask_events_by_owner(owner_user_id=share.user_id, since=since)
            if share_count >= share.daily_ask_limit:
                await _record_public_ask_event(repository, share, client_key, query, "blocked", "share_daily_cap")
                await session.commit()
                logger.warning("public_collection_ask_daily_cap_exceeded", extra={"slug": slug})
                raise ValidationException("public collection ask limit reached")
            if owner_count >= _PUBLIC_COLLECTION_OWNER_DAILY_CAP:
                await _record_public_ask_event(repository, share, client_key, query, "blocked", "owner_daily_cap")
                await session.commit()
                logger.warning("public_collection_owner_daily_cap_exceeded", extra={"owner_user_id": str(share.user_id)})
                raise ValidationException("public collection ask limit reached")

            reservation_id = await _record_public_ask_event(repository, share, client_key, query, "reserved", None)
            await session.commit()
            return PublicAskReservation(id=reservation_id, share=share)

    async def complete(self, reservation: PublicAskReservation, *, result: QueryResult) -> AnswerShareRecord:
        async with self._session_factory() as session:
            answer_share = await _create_answer_share(
                session,
                user_id=reservation.share.user_id,
                collection_id=reservation.share.collection_id,
                conversation_id=None,
                public_collection_slug=reservation.share.slug,
                query_text=result.query,
                answer_text=result.answer,
                sources=result.sources,
            )
            repository = CollectionShareRepository.from_session(session)
            await repository.update_public_ask_event(
                event_id=reservation.id,
                status="allowed",
                reason=None,
                answer_share_slug=answer_share.slug,
            )
            await session.commit()
            return answer_share

    async def fail(self, reservation_id: UUID) -> None:
        async with self._session_factory() as session:
            repository = CollectionShareRepository.from_session(session)
            await repository.update_public_ask_event(
                event_id=reservation_id,
                status="failed",
                reason="query_failed",
            )
            await session.commit()


class PublicShareService:
    def __init__(self, public_ask_ledger: PublicAskLedger | None = None) -> None:
        self._public_ask_ledger = public_ask_ledger

    async def get_public_collection(self, session: AsyncSession, *, slug: str) -> PublicCollectionResponse:
        repository = CollectionShareRepository.from_session(session)
        collection = await repository.get_public_collection(slug)
        if collection is None:
            raise ResourceNotFoundException("public collection not found")
        return to_public_collection_response(collection)

    async def get_public_answer_share(self, session: AsyncSession, *, slug: str) -> PublicAnswerShareResponse:
        repository = AnswerShareRepository.from_session(session)
        share = await repository.get_active_by_slug(slug)
        if share is None:
            raise ResourceNotFoundException("answer share not found")
        return to_public_answer_share_response(share)

    async def list_answer_shares(
        self,
        session: AsyncSession,
        *,
        user_id: UUID,
        limit: int,
        offset: int,
    ) -> AnswerShareListResponse:
        repository = AnswerShareRepository.from_session(session)
        shares = await repository.list_by_user_id(
            user_id=user_id,
            limit=max(1, min(limit, 100)),
            offset=max(0, offset),
        )
        return to_answer_share_list_response(shares)

    async def revoke_answer_share(self, session: AsyncSession, *, user_id: UUID, slug: str) -> None:
        repository = AnswerShareRepository.from_session(session)
        revoked = await repository.revoke_by_slug(
            user_id=user_id,
            slug=slug,
            revoked_at=datetime.now(UTC),
        )
        if not revoked:
            raise ResourceNotFoundException("answer share not found")
        await session.flush()

    async def create_answer_share(
        self,
        session: AsyncSession,
        *,
        user_id: UUID,
        query_text: str,
        answer_text: str,
        sources: Sequence[QuerySource],
        collection_id: UUID | None = None,
        conversation_id: UUID | None = None,
        public_collection_slug: str | None = None,
    ) -> AnswerShareRecord:
        return await _create_answer_share(
            session,
            user_id=user_id,
            query_text=query_text,
            answer_text=answer_text,
            sources=sources,
            collection_id=collection_id,
            conversation_id=conversation_id,
            public_collection_slug=public_collection_slug,
        )

    async def query_public_collection(
        self,
        *,
        graph_runner: QueryGraphRunner,
        slug: str,
        query: str,
        client_key: str,
        limit: int,
    ) -> PublicCollectionQueryResponse:
        query_result = await self.create_public_collection_query_result(
            graph_runner=graph_runner,
            slug=slug,
            query=query,
            client_key=client_key,
            limit=limit,
        )
        return PublicCollectionQueryResponse.model_validate(
            {
                "query": query_result.result.query,
                "answer": query_result.result.answer,
                "sources": [
                    to_public_query_source_response(source, index).model_dump()
                    for index, source in enumerate(query_result.result.sources, start=1)
                ],
                "suggested_follow_up_questions": query_result.result.suggested_follow_up_questions,
                "share": to_public_answer_share_response(query_result.share).model_dump(),
            }
        )

    async def create_public_collection_query_result(
        self,
        *,
        graph_runner: QueryGraphRunner,
        slug: str,
        query: str,
        client_key: str,
        limit: int,
    ) -> PublicCollectionQueryResult:
        normalized_query = query.strip()
        if self._public_ask_ledger is None:
            raise ApplicationStateException("public Ask ledger is not configured")
        reservation = await self._public_ask_ledger.reserve(
            slug=slug,
            query=normalized_query,
            client_key=client_key,
        )
        try:
            conversation_id = uuid.uuid4()
            state = await graph_runner.run(
                ConseriumQueryState(
                    query=normalized_query,
                    user_id=reservation.share.user_id,
                    limit=max(1, min(limit, 8)),
                    conversation_id=conversation_id,
                    collection_id=reservation.share.collection_id,
                    conversation_turns=[],
                )
            )
            if state.refrag_context is None:
                raise ApplicationStateException("public query did not produce refrag_context")

            state.sources = mark_sources_used_in_answer(state.sources, state.answer)
            result = QueryResult(
                conversation_id=conversation_id,
                query=normalized_query,
                answer=state.answer,
                sources=state.sources,
                refrag_context=state.refrag_context,
                debug=query_debug(normalized_query, state),
                suggested_follow_up_questions=build_follow_up_questions(state.answer, state.sources),
            )
            answer_share = await self._public_ask_ledger.complete(reservation, result=result)
            return PublicCollectionQueryResult(result=result, share=answer_share)
        except Exception:
            await self._public_ask_ledger.fail(reservation.id)
            raise


def to_public_collection_response(dto: PublicCollectionResult) -> PublicCollectionResponse:
    return PublicCollectionResponse(
        id=dto.id,
        name=dto.name,
        description=dto.description,
        color=dto.color,
        documents=[to_public_collection_document_response(document) for document in dto.documents],
        created_at=dto.created_at,
        updated_at=dto.updated_at,
    )


def to_public_collection_document_response(dto: PublicCollectionDocument) -> PublicCollectionDocumentResponse:
    return PublicCollectionDocumentResponse(
        id=dto.id,
        title=dto.title,
        type=dto.type,
        status=dto.status,
        source_url=dto.source_url,
        summary=dto.summary,
        word_count=dto.word_count,
        language=dto.language,
        tags=dto.tags,
        created_at=dto.created_at,
        updated_at=dto.updated_at,
    )


def to_answer_share_response(dto: AnswerShareRecord) -> AnswerShareResponse:
    return AnswerShareResponse(
        slug=dto.slug,
        url_path=f"/public/answers/{dto.slug}",
        query=dto.query_text,
        answer=dto.answer_text,
        sources=[to_answer_share_source_response(source) for source in dto.sources],
        collection_id=dto.collection_id,
        collection_name=dto.collection_name,
        public_collection_slug=dto.public_collection_slug,
        created_at=dto.created_at,
        revoked_at=dto.revoked_at,
    )


def to_answer_share_list_response(dtos: list[AnswerShareRecord]) -> AnswerShareListResponse:
    return AnswerShareListResponse(items=[to_answer_share_response(dto) for dto in dtos])


def to_public_answer_share_response(dto: AnswerShareRecord) -> PublicAnswerShareResponse:
    return PublicAnswerShareResponse(
        slug=dto.slug,
        url_path=f"/public/answers/{dto.slug}",
        query=dto.query_text,
        answer=dto.answer_text,
        sources=[to_public_answer_share_source_response(source) for source in dto.sources],
        public_collection_slug=dto.public_collection_slug,
        created_at=dto.created_at,
    )


def to_public_answer_share_source_response(dto: AnswerShareSource) -> PublicAnswerShareSourceResponse:
    return PublicAnswerShareSourceResponse(
        document_title=dto.document_title,
        content=dto.content,
        page_number=dto.page_number,
        chunk_index=dto.chunk_index,
        citation=dto.citation,
        used_in_answer=dto.used_in_answer,
    )


def to_answer_share_source_response(dto: AnswerShareSource) -> AnswerShareSourceResponse:
    return AnswerShareSourceResponse(
        chunk_id=dto.chunk_id,
        document_id=dto.document_id,
        document_title=dto.document_title,
        content=dto.content,
        page_number=dto.page_number,
        chunk_index=dto.chunk_index,
        citation=dto.citation,
        used_in_answer=dto.used_in_answer,
    )


def to_public_query_source_response(dto: QuerySource, index: int) -> PublicQuerySourceResponse:
    return PublicQuerySourceResponse(
        document_title=dto.document_title,
        content=dto.content,
        page_number=dto.page_number,
        chunk_index=dto.chunk_index,
        citation=f"[{index}]",
        used_in_answer=dto.used_in_answer,
    )


def to_answer_share_source(source: QuerySource, index: int) -> AnswerShareSource:
    return AnswerShareSource(
        chunk_id=source.chunk_id,
        document_id=source.document_id,
        document_title=source.document_title,
        content=source.content,
        page_number=source.page_number,
        chunk_index=source.chunk_index,
        citation=f"[{index}]",
        used_in_answer=source.used_in_answer,
    )


async def _create_answer_share(
    session: AsyncSession,
    *,
    user_id: UUID,
    query_text: str,
    answer_text: str,
    sources: Sequence[QuerySource],
    collection_id: UUID | None,
    conversation_id: UUID | None,
    public_collection_slug: str | None,
) -> AnswerShareRecord:
    repository = AnswerShareRepository.from_session(session)
    share_sources = [to_answer_share_source(source, index) for index, source in enumerate(sources, start=1)]
    for _ in range(5):
        slug = secrets.token_urlsafe(12)
        if await repository.get_active_by_slug(slug) is not None:
            continue
        return await repository.create(
            id=uuid.uuid4(),
            slug=slug,
            user_id=user_id,
            collection_id=collection_id,
            conversation_id=conversation_id,
            public_collection_slug=public_collection_slug,
            query_text=query_text,
            answer_text=answer_text,
            sources=share_sources,
        )
    raise ApplicationStateException("could not create answer share")


async def _record_public_ask_event(
    repository: CollectionShareRepository,
    share: CollectionShareRecord,
    client_key: str,
    query_text: str,
    status: str,
    reason: str | None,
    *,
    answer_share_slug: str | None = None,
) -> UUID:
    event_id = uuid.uuid4()
    await repository.record_public_ask_event(
        id=event_id,
        share_slug=share.slug,
        collection_share_id=share.id,
        owner_user_id=share.user_id,
        client_key=client_key,
        status=status,
        reason=reason,
        query_text=query_text[:4000],
        answer_share_slug=answer_share_slug,
    )
    return event_id
