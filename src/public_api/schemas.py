from pydantic import BaseModel

from src.documents.schemas import DocumentResponse
from src.webhooks.schemas import ExternalIngestRequest, ExternalIntakeItemResponse


class PublicIngestRequest(ExternalIngestRequest): ...


class PublicIngestResponse(BaseModel):
    intake_item: ExternalIntakeItemResponse
    document: DocumentResponse | None
