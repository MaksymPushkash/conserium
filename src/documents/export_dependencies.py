from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.documents.activity_repository import DocumentActivityRepository
from src.documents.document_repository import DocumentRepository
from src.documents.exports import DocumentExporter
from src.postgres import get_db_session


def get_document_exporter(session: AsyncSession = Depends(get_db_session)) -> DocumentExporter:
    return DocumentExporter(
        session,
        DocumentRepository.from_session(session),
        DocumentActivityRepository.from_session(session),
    )
