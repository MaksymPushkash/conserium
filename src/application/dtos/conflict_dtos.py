from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, final

if TYPE_CHECKING:
    from uuid import UUID


@final
@dataclass(frozen=True, slots=True)
class ConflictClaimRecordDTO:
    document_id: UUID
    subject: str
    polarity: str
    evidence: str


@final
@dataclass(frozen=True, slots=True)
class PersistedConflictRecordDTO:
    subject: str
    summary: str
    document_ids: list[UUID]
    evidence: list[str]
    score: float


@final
@dataclass(frozen=True, slots=True)
class ConflictDetectionDTO:
    user_id: UUID
    collection_id: UUID | None = None
    limit: int = 100


@final
@dataclass(frozen=True, slots=True)
class ConflictDocumentDTO:
    id: UUID
    title: str


@final
@dataclass(frozen=True, slots=True)
class ConflictFindingDTO:
    subject: str
    summary: str
    documents: list[ConflictDocumentDTO]
    evidence: list[str]
    score: float


@final
@dataclass(frozen=True, slots=True)
class ConflictDetectionResultDTO:
    collection_id: UUID | None
    analyzed_document_count: int
    conflicts: list[ConflictFindingDTO]
