from uuid import UUID

from src.documents.document_repository import DocumentRepository
from src.documents.status import DocumentStatus
from src.postgres import AsyncSession


class ObservabilityRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._documents = DocumentRepository.from_session(session)

    async def count_failed_documents(self, user_id: UUID) -> int:
        return await self._documents.count_by_user_id(user_id=user_id, status=DocumentStatus.FAILED)


__all__ = ["ObservabilityRepository"]
