from dataclasses import dataclass
from datetime import datetime
from typing import final
from uuid import UUID

from src.domain.value_objects.document_status import DocumentStatus


@final
@dataclass(frozen=True, slots=True)
class NoteDTO:
    id: UUID
    title: str
    content: str
    status: DocumentStatus
    word_count: int
    language: str | None
    created_at: datetime
    updated_at: datetime | None


@final
@dataclass(frozen=True, slots=True)
class NoteListItemDTO:
    id: UUID
    title: str
    status: DocumentStatus
    word_count: int
    language: str | None
    created_at: datetime
    updated_at: datetime | None


@final
@dataclass(frozen=True, slots=True)
class NoteListDTO:
    items: list[NoteListItemDTO]
    total: int
    limit: int
    offset: int


@final
@dataclass(frozen=True, slots=True)
class CreateNoteDTO:
    user_id: UUID
    title: str | None = None
    content: str | None = None
    language: str | None = None


@final
@dataclass(frozen=True, slots=True)
class UpdateNoteDTO:
    user_id: UUID
    note_id: UUID
    title: str
    content: str
    language: str | None = None


@final
@dataclass(frozen=True, slots=True)
class GetNoteDTO:
    user_id: UUID
    note_id: UUID


@final
@dataclass(frozen=True, slots=True)
class ListNotesDTO:
    user_id: UUID
    limit: int = 100
    offset: int = 0
