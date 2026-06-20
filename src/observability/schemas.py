from pydantic import BaseModel, Field


class QueryLatencySummary(BaseModel):
    count: float
    average_seconds: float


class RetrievalSummary(BaseModel):
    hit_rate: float
    requests: float
    hits: float


class DocumentProcessingSummary(BaseModel):
    failed_processing_count: int


class OpenAISummary(BaseModel):
    estimated_cost_usd: float


class ObservabilitySummaryResponse(BaseModel):
    query_latency: QueryLatencySummary
    retrieval: RetrievalSummary
    documents: DocumentProcessingSummary
    openai: OpenAISummary
    queues: dict[str, float] = Field(default_factory=dict)
