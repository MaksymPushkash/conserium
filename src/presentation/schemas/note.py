from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

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


class NoteListItemResponse(BaseModel):
    id: UUID
    title: str
    status: DocumentStatus
    word_count: int
    language: str | None
    created_at: datetime
    updated_at: datetime | None


class NoteListResponse(BaseModel):
    items: list[NoteListItemResponse]
    total: int
    limit: int
    offset: int
