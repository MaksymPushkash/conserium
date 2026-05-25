from pydantic import BaseModel, Field


class KnowledgeGapAreaResponse(BaseModel):
    id: str
    name: str
    covered: bool
    evidence_count: int
    evidence_titles: list[str] = Field(default_factory=list)
    why_detected: str
    missing_source_types: list[str] = Field(default_factory=list)
    severity: str
    rationale: str
    suggested_actions: list[str] = Field(default_factory=list)


class KnowledgeGapResponse(BaseModel):
    id: str
    topic: str
    collection_id: str | None = None
    covered_count: int
    missing_count: int
    coverage_ratio: float
    why_detected: str
    missing_source_types: list[str] = Field(default_factory=list)
    severity: str
    rationale: str
    suggested_actions: list[str] = Field(default_factory=list)
    areas: list[KnowledgeGapAreaResponse] = Field(default_factory=list)


class KnowledgeGapListResponse(BaseModel):
    items: list[KnowledgeGapResponse]
    total: int


class KnowledgeGapNoteRequest(BaseModel):
    topic: str = Field(min_length=1, max_length=100)
    area_name: str = Field(min_length=1, max_length=100)
    collection_id: str | None = None
