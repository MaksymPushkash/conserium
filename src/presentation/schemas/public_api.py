from pydantic import BaseModel

from src.presentation.schemas.document import DocumentResponse
from src.presentation.schemas.external_intake import ExternalIngestRequest, ExternalIntakeItemResponse


class PublicIngestRequest(ExternalIngestRequest): ...


class PublicIngestResponse(BaseModel):
    intake_item: ExternalIntakeItemResponse
    document: DocumentResponse | None
