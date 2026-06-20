from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import func, select

from src.documents.repository import NoteVersionRecord
from src.models.note_version import NoteVersionModel

if TYPE_CHECKING:
    from uuid import UUID

    from sqlalchemy.ext.asyncio import AsyncSession


class NoteVersionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @classmethod
    def from_session(cls, session: AsyncSession) -> NoteVersionRepository:
        return cls(session)

    async def create(self, version: NoteVersionRecord) -> None:
        self._session.add(
            NoteVersionModel(
                id=version.id,
                note_id=version.note_id,
                user_id=version.user_id,
                version_number=version.version_number,
                title=version.title,
                content=version.content,
            )
        )

    async def list_by_note_id(self, *, note_id: UUID, user_id: UUID) -> list[NoteVersionRecord]:
        result = await self._session.execute(
            select(NoteVersionModel)
            .where(NoteVersionModel.note_id == note_id, NoteVersionModel.user_id == user_id)
            .order_by(NoteVersionModel.version_number.desc())
        )
        return [self._to_record(model) for model in result.scalars().all()]

    async def get_by_id(self, *, version_id: UUID, note_id: UUID, user_id: UUID) -> NoteVersionRecord | None:
        result = await self._session.execute(
            select(NoteVersionModel).where(
                NoteVersionModel.id == version_id,
                NoteVersionModel.note_id == note_id,
                NoteVersionModel.user_id == user_id,
            )
        )
        model = result.scalar_one_or_none()
        return self._to_record(model) if model else None

    async def count_by_note_id(self, note_id: UUID) -> int:
        result = await self._session.execute(
            select(func.count()).select_from(NoteVersionModel).where(NoteVersionModel.note_id == note_id)
        )
        return int(result.scalar_one())

    @staticmethod
    def _to_record(model: NoteVersionModel) -> NoteVersionRecord:
        return NoteVersionRecord(
            id=model.id,
            note_id=model.note_id,
            user_id=model.user_id,
            version_number=model.version_number,
            title=model.title,
            content=model.content,
            created_at=model.created_at,
        )
