from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class KnowledgeGapAreaDTO:
    id: str
    name: str
    covered: bool
    evidence_count: int
    evidence_titles: list[str]
    why_detected: str
    missing_source_types: list[str]
    severity: str
    rationale: str
    suggested_actions: list[str]


@dataclass(frozen=True, slots=True)
class KnowledgeGapDTO:
    id: str
    topic: str
    collection_id: UUID | None
    covered_count: int
    missing_count: int
    coverage_ratio: float
    why_detected: str
    missing_source_types: list[str]
    severity: str
    rationale: str
    suggested_actions: list[str]
    areas: list[KnowledgeGapAreaDTO]


@dataclass(frozen=True, slots=True)
class KnowledgeGapListDTO:
    items: list[KnowledgeGapDTO]
    total: int
