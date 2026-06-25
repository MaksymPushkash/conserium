from dataclasses import dataclass
from typing import final
from uuid import UUID

from pydantic import BaseModel


@final
@dataclass(frozen=True, slots=True)
class ConflictClaimRecord:
    document_id: UUID
    subject: str
    polarity: str
    evidence: str


@final
@dataclass(frozen=True, slots=True)
class PersistedConflictRecord:
    subject: str
    summary: str
    document_ids: list[UUID]
    evidence: list[str]
    score: float


@final
@dataclass(frozen=True, slots=True)
class ConflictDocument:
    id: UUID
    title: str


@final
@dataclass(frozen=True, slots=True)
class ConflictFinding:
    subject: str
    summary: str
    documents: list[ConflictDocument]
    evidence: list[str]
    score: float


@final
@dataclass(frozen=True, slots=True)
class ConflictDetectionResult:
    collection_id: UUID | None
    analyzed_document_count: int
    conflicts: list[ConflictFinding]


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
