from __future__ import annotations

from uuid import UUID  # noqa: TC003

from pydantic import BaseModel


class ConflictDocumentResponse(BaseModel):
    id: UUID
    title: str


class ConflictFindingResponse(BaseModel):
    subject: str
    summary: str
    documents: list[ConflictDocumentResponse]
    evidence: list[str]
    score: float


class ConflictDetectionResponse(BaseModel):
    collection_id: UUID | None
    analyzed_document_count: int
    conflicts: list[ConflictFindingResponse]
