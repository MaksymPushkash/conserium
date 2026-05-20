from uuid import UUID

from pydantic import BaseModel, Field

from src.presentation.schemas.query import QuerySourceResponse


class CompareDocumentsRequest(BaseModel):
    left_document_id: UUID
    right_document_id: UUID
    prompt: str | None = Field(default=None, max_length=1000)
    limit: int = Field(default=12, ge=2, le=30)


class CompareDocumentsResponse(BaseModel):
    left_document_id: UUID
    right_document_id: UUID
    left_title: str
    right_title: str
    markdown: str
    sources: list[QuerySourceResponse]
