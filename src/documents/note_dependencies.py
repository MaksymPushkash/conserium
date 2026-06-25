from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.documents.chunk_repository import ChunkRepository
from src.documents.dependencies import (
    get_chunk_repository,
    get_document_collection_access,
    get_document_processing_service,
    get_document_repository,
)
from src.documents.document_repository import DocumentRepository
from src.documents.note_version_repository import NoteVersionRepository
from src.documents.notes import NoteService
from src.documents.processing import DocumentProcessingService
from src.documents.service import DocumentCollectionAccess
from src.postgres import get_db_session


def get_note_version_repository(session: AsyncSession = Depends(get_db_session)) -> NoteVersionRepository:
    return NoteVersionRepository.from_session(session)


def get_note_service(
    session: AsyncSession = Depends(get_db_session),
    document_repo: DocumentRepository = Depends(get_document_repository),
    collection_access: DocumentCollectionAccess = Depends(get_document_collection_access),
    note_version_repo: NoteVersionRepository = Depends(get_note_version_repository),
    processing_service: DocumentProcessingService = Depends(get_document_processing_service),
    chunk_repo: ChunkRepository = Depends(get_chunk_repository),
) -> NoteService:
    return NoteService(session, document_repo, collection_access, note_version_repo, processing_service, chunk_repo)
