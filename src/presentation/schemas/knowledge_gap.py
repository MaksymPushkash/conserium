from pydantic import BaseModel, Field


class KnowledgeGapAreaResponse(BaseModel):
    name: str
    covered: bool
    evidence_count: int
    evidence_titles: list[str] = Field(default_factory=list)


class KnowledgeGapResponse(BaseModel):
    topic: str
    covered_count: int
    missing_count: int
    coverage_ratio: float
    areas: list[KnowledgeGapAreaResponse] = Field(default_factory=list)
