from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from src.application.dtos.note_dtos import NoteDTO, NoteListDTO, NoteListItemDTO
from src.domain.value_objects.document_status import DocumentStatus


class CreateNoteRequest(BaseModel):
    title: str | None = Field(default=None, max_length=120)
    content: str | None = None
    language: str | None = Field(default=None, max_length=10)


class UpdateNoteRequest(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    content: str = ""
    language: str | None = Field(default=None, max_length=10)


class NoteResponse(BaseModel):
    id: UUID
    title: str
    content: str
    status: DocumentStatus
    word_count: int
    language: str | None
    created_at: datetime
    updated_at: datetime | None

    @classmethod
    def from_dto(cls, dto: NoteDTO) -> "NoteResponse":
        return cls(
            id=dto.id,
            title=dto.title,
            content=dto.content,
            status=dto.status,
            word_count=dto.word_count,
            language=dto.language,
            created_at=dto.created_at,
            updated_at=dto.updated_at,
        )


class NoteListItemResponse(BaseModel):
    id: UUID
    title: str
    status: DocumentStatus
    word_count: int
    language: str | None
    created_at: datetime
    updated_at: datetime | None

    @classmethod
    def from_dto(cls, dto: NoteListItemDTO) -> "NoteListItemResponse":
        return cls(
            id=dto.id,
            title=dto.title,
            status=dto.status,
            word_count=dto.word_count,
            language=dto.language,
            created_at=dto.created_at,
            updated_at=dto.updated_at,
        )


class NoteListResponse(BaseModel):
    items: list[NoteListItemResponse]
    total: int
    limit: int
    offset: int

    @classmethod
    def from_dto(cls, dto: NoteListDTO) -> "NoteListResponse":
        return cls(
            items=[NoteListItemResponse.from_dto(item) for item in dto.items],
            total=dto.total,
            limit=dto.limit,
            offset=dto.offset,
        )
