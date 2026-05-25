from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.application.dtos.query_dtos import QuerySourceDTO
from src.application.ports.persistence.draft_repository import DraftRecord, DraftVersionRecord, IDraftRepository
from src.infrastructure.database.models.draft import DraftModel, DraftVersionModel


class SQLAlchemyDraftRepository(IDraftRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_with_version(self, *, draft: DraftRecord, version: DraftVersionRecord) -> DraftRecord:
        draft_model = DraftModel(
            id=draft.id,
            user_id=draft.user_id,
            collection_id=draft.collection_id,
            current_version_id=version.id,
            title=draft.title,
            prompt=draft.prompt,
            template_id=draft.template_id,
            scope_type=draft.scope_type,
            topic=draft.topic,
            knowledge_gap_id=draft.knowledge_gap_id,
            scope_metadata=draft.scope_metadata,
            markdown=draft.markdown,
            source_metadata=sources_to_json(draft.sources),
            gaps=draft.gaps,
            version_number=version.version_number,
        )
        self._session.add(draft_model)
        self._session.add(version_to_model(version))
        await self._session.flush()
        await self._session.refresh(draft_model)
        return self._to_record(draft_model)

    async def append_version(self, *, draft_id: UUID, version: DraftVersionRecord) -> DraftRecord:
        result = await self._session.execute(select(DraftModel).where(DraftModel.id == draft_id))
        draft = result.scalar_one()
        draft.current_version_id = version.id
        draft.collection_id = version.collection_id
        draft.title = version.title
        draft.prompt = version.prompt
        draft.template_id = version.template_id
        draft.scope_type = version.scope_type
        draft.topic = version.topic
        draft.knowledge_gap_id = version.knowledge_gap_id
        draft.scope_metadata = version.scope_metadata
        draft.markdown = version.markdown
        draft.source_metadata = sources_to_json(version.sources)
        draft.gaps = version.gaps
        draft.version_number = version.version_number
        self._session.add(version_to_model(version))
        await self._session.flush()
        await self._session.refresh(draft)
        return self._to_record(draft)

    async def get_by_id(self, draft_id: UUID) -> DraftRecord | None:
        result = await self._session.execute(select(DraftModel).where(DraftModel.id == draft_id))
        model = result.scalar_one_or_none()
        return self._to_record(model) if model else None

    async def list_by_user_id(
        self,
        *,
        user_id: UUID,
        collection_id: UUID | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[DraftRecord]:
        statement = select(DraftModel).where(DraftModel.user_id == user_id)
        if collection_id is not None:
            statement = statement.where(DraftModel.collection_id == collection_id)
        result = await self._session.execute(
            statement.order_by(DraftModel.updated_at.desc().nullslast(), DraftModel.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return [self._to_record(model) for model in result.scalars().all()]

    async def list_versions(self, *, draft_id: UUID, user_id: UUID) -> list[DraftVersionRecord]:
        result = await self._session.execute(
            select(DraftVersionModel)
            .where(DraftVersionModel.draft_id == draft_id, DraftVersionModel.user_id == user_id)
            .order_by(DraftVersionModel.version_number.desc())
        )
        return [version_from_model(model) for model in result.scalars().all()]

    async def get_version(self, *, draft_id: UUID, version_id: UUID, user_id: UUID) -> DraftVersionRecord | None:
        result = await self._session.execute(
            select(DraftVersionModel).where(
                DraftVersionModel.id == version_id,
                DraftVersionModel.draft_id == draft_id,
                DraftVersionModel.user_id == user_id,
            )
        )
        model = result.scalar_one_or_none()
        return version_from_model(model) if model else None

    async def restore_version(self, *, version: DraftVersionRecord) -> DraftRecord:
        result = await self._session.execute(select(DraftModel).where(DraftModel.id == version.draft_id))
        draft = result.scalar_one()
        draft.current_version_id = version.id
        draft.collection_id = version.collection_id
        draft.title = version.title
        draft.prompt = version.prompt
        draft.template_id = version.template_id
        draft.scope_type = version.scope_type
        draft.topic = version.topic
        draft.knowledge_gap_id = version.knowledge_gap_id
        draft.scope_metadata = version.scope_metadata
        draft.markdown = version.markdown
        draft.source_metadata = sources_to_json(version.sources)
        draft.gaps = version.gaps
        draft.version_number = version.version_number
        await self._session.flush()
        await self._session.refresh(draft)
        return self._to_record(draft)

    async def delete(self, draft_id: UUID) -> None:
        await self._session.execute(delete(DraftModel).where(DraftModel.id == draft_id))

    @staticmethod
    def _to_record(model: DraftModel) -> DraftRecord:
        return DraftRecord(
            id=model.id,
            user_id=model.user_id,
            collection_id=model.collection_id,
            title=model.title,
            prompt=model.prompt,
            template_id=model.template_id,
            scope_type=model.scope_type,
            topic=model.topic,
            knowledge_gap_id=model.knowledge_gap_id,
            scope_metadata=model.scope_metadata,
            markdown=model.markdown,
            sources=sources_from_json(model.source_metadata),
            gaps=list(model.gaps),
            current_version_id=model.current_version_id,
            version_number=model.version_number,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )


def version_to_model(version: DraftVersionRecord) -> DraftVersionModel:
    return DraftVersionModel(
        id=version.id,
        draft_id=version.draft_id,
        user_id=version.user_id,
        version_number=version.version_number,
        title=version.title,
        prompt=version.prompt,
        template_id=version.template_id,
        scope_type=version.scope_type,
        collection_id=version.collection_id,
        topic=version.topic,
        knowledge_gap_id=version.knowledge_gap_id,
        scope_metadata=version.scope_metadata,
        markdown=version.markdown,
        source_metadata=sources_to_json(version.sources),
        gaps=version.gaps,
    )


def version_from_model(model: DraftVersionModel) -> DraftVersionRecord:
    return DraftVersionRecord(
        id=model.id,
        draft_id=model.draft_id,
        user_id=model.user_id,
        version_number=model.version_number,
        title=model.title,
        prompt=model.prompt,
        template_id=model.template_id,
        scope_type=model.scope_type,
        collection_id=model.collection_id,
        topic=model.topic,
        knowledge_gap_id=model.knowledge_gap_id,
        scope_metadata=model.scope_metadata,
        markdown=model.markdown,
        sources=sources_from_json(model.source_metadata),
        gaps=list(model.gaps),
        created_at=model.created_at,
    )


def sources_to_json(sources: list[QuerySourceDTO]) -> list[dict[str, object]]:
    return [
        {
            "chunk_id": str(source.chunk_id),
            "document_id": str(source.document_id),
            "document_title": source.document_title,
            "content": source.content,
            "page_number": source.page_number,
            "chunk_index": source.chunk_index,
            "score": source.score,
            "used_in_answer": source.used_in_answer,
        }
        for source in sources
    ]


def sources_from_json(items: list[dict[str, object]]) -> list[QuerySourceDTO]:
    return [
        QuerySourceDTO(
            chunk_id=UUID(str(item["chunk_id"])),
            document_id=UUID(str(item["document_id"])),
            document_title=str(item["document_title"]) if item.get("document_title") is not None else None,
            content=str(item.get("content") or ""),
            page_number=maybe_int(item.get("page_number")),
            chunk_index=maybe_int(item.get("chunk_index")) or 0,
            score=maybe_float(item.get("score")),
            used_in_answer=bool(item.get("used_in_answer")),
        )
        for item in items
    ]


def maybe_int(value: object) -> int | None:
    if value is None:
        return None
    return int(str(value))


def maybe_float(value: object) -> float | None:
    if value is None:
        return None
    return float(str(value))
