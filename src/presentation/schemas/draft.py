from uuid import UUID

from pydantic import BaseModel, Field

from src.domain.value_objects.document_type import DocumentType
from src.presentation.schemas.query import QuerySourceResponse


class DraftGenerateRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=2000)
    collection_id: UUID | None = None
    tag_names: list[str] | None = Field(default=None, max_length=20)
    document_types: list[DocumentType] | None = None
    limit: int = Field(default=8, ge=1, le=20)


class DraftResponse(BaseModel):
    prompt: str
    markdown: str
    sources: list[QuerySourceResponse]
    gaps: list[str]
