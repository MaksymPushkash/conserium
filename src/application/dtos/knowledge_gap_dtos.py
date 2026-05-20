from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class KnowledgeGapAreaDTO:
    name: str
    covered: bool
    evidence_count: int
    evidence_titles: list[str]


@dataclass(frozen=True, slots=True)
class KnowledgeGapDTO:
    topic: str
    covered_count: int
    missing_count: int
    coverage_ratio: float
    areas: list[KnowledgeGapAreaDTO]
