import uuid
from datetime import UTC, datetime
from typing import cast

import pytest

from src.application.dtos.document_dtos import CreateDocumentDTO, DeleteDocumentDTO, GetDocumentDTO, ListDocumentsDTO
from src.application.interfaces.unit_of_work import IUnitOfWork
from src.application.use_cases.documents.create_document_use_case import CreateDocumentUseCase
from src.application.use_cases.documents.delete_document_use_case import DeleteDocumentUseCase
from src.application.use_cases.documents.get_document_use_case import GetDocumentUseCase
from src.application.use_cases.documents.list_documents_use_case import ListDocumentsUseCase
from src.domain.entities.document_entity import DocumentEntity
from src.domain.exceptions import DocumentAccessDeniedException, DocumentNotFoundException
from src.domain.value_objects.document_status import DocumentStatus
from src.domain.value_objects.document_type import DocumentType


class _FakeDocumentRepository:
    def __init__(self, documents: list[DocumentEntity] | None = None) -> None:
        self.documents = {document.id: document for document in documents or []}
        self.created: list[DocumentEntity] = []
        self.deleted: list[uuid.UUID] = []

    async def get_by_id(self, document_id: uuid.UUID) -> DocumentEntity | None:
        return self.documents.get(document_id)

    async def get_by_user_id(self, user_id: uuid.UUID, *, limit: int = 50, offset: int = 0) -> list[DocumentEntity]:
        documents = [document for document in self.documents.values() if document.user_id == user_id]
        return documents[offset : offset + limit]

    async def create(self, document: DocumentEntity) -> None:
        self.created.append(document)
        self.documents[document.id] = document

    async def update(self, document: DocumentEntity) -> None:
        self.documents[document.id] = document

    async def delete(self, document_id: uuid.UUID) -> None:
        self.deleted.append(document_id)
        self.documents.pop(document_id, None)

    async def exists(self, document_id: uuid.UUID) -> bool:
        return document_id in self.documents

    async def count_by_user_id(self, user_id: uuid.UUID) -> int:
        return len([document for document in self.documents.values() if document.user_id == user_id])


class _FakeUnitOfWork:
    def __init__(self, document_repo: _FakeDocumentRepository) -> None:
        self.document_repo = document_repo
        self.committed = False
        self.rolled_back = False

    async def __aenter__(self) -> "_FakeUnitOfWork":
        return self

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        if exc_type is not None:
            self.rolled_back = True

    async def commit(self) -> None:
        self.committed = True

    async def rollback(self) -> None:
        self.rolled_back = True


def _as_uow(uow: _FakeUnitOfWork) -> IUnitOfWork:
    return cast("IUnitOfWork", uow)


def _make_document(*, user_id: uuid.UUID | None = None) -> DocumentEntity:
    return DocumentEntity(
        id=uuid.uuid4(),
        user_id=user_id or uuid.uuid4(),
        collection_id=None,
        title="Saved note",
        type=DocumentType.TEXT,
        status=DocumentStatus.PENDING,
        source_url=None,
        file_path=None,
        file_size_bytes=None,
        raw_content="Important text",
        summary=None,
        word_count=2,
        language="en",
        doc_embedding=None,
        is_duplicate=False,
        duplicate_of_id=None,
        created_at=datetime.now(UTC),
        updated_at=None,
    )


async def test_create_document_use_case_creates_pending_document() -> None:
    user_id = uuid.uuid4()
    document_repo = _FakeDocumentRepository()
    uow = _FakeUnitOfWork(document_repo)
    use_case = CreateDocumentUseCase(_as_uow(uow))

    result = await use_case(
        CreateDocumentDTO(
            user_id=user_id,
            title="New note",
            type=DocumentType.TEXT,
            raw_content="Hello",
            word_count=1,
            language="en",
        )
    )

    assert result.user_id == user_id
    assert result.title == "New note"
    assert result.status == DocumentStatus.PENDING
    assert len(document_repo.created) == 1
    assert uow.committed is True


async def test_list_documents_use_case_returns_paginated_documents() -> None:
    user_id = uuid.uuid4()
    own_document = _make_document(user_id=user_id)
    other_document = _make_document()
    document_repo = _FakeDocumentRepository([own_document, other_document])
    use_case = ListDocumentsUseCase(_as_uow(_FakeUnitOfWork(document_repo)))

    result = await use_case(ListDocumentsDTO(user_id=user_id, limit=10, offset=0))

    assert result.total == 1
    assert len(result.items) == 1
    assert result.items[0].id == own_document.id


async def test_get_document_use_case_returns_owned_document() -> None:
    user_id = uuid.uuid4()
    document = _make_document(user_id=user_id)
    use_case = GetDocumentUseCase(_as_uow(_FakeUnitOfWork(_FakeDocumentRepository([document]))))

    result = await use_case(GetDocumentDTO(user_id=user_id, document_id=document.id))

    assert result.id == document.id


async def test_get_document_use_case_raises_for_missing_document() -> None:
    use_case = GetDocumentUseCase(_as_uow(_FakeUnitOfWork(_FakeDocumentRepository())))

    with pytest.raises(DocumentNotFoundException):
        await use_case(GetDocumentDTO(user_id=uuid.uuid4(), document_id=uuid.uuid4()))


async def test_get_document_use_case_raises_for_foreign_document() -> None:
    document = _make_document()
    use_case = GetDocumentUseCase(_as_uow(_FakeUnitOfWork(_FakeDocumentRepository([document]))))

    with pytest.raises(DocumentAccessDeniedException):
        await use_case(GetDocumentDTO(user_id=uuid.uuid4(), document_id=document.id))


async def test_delete_document_use_case_deletes_owned_document() -> None:
    user_id = uuid.uuid4()
    document = _make_document(user_id=user_id)
    document_repo = _FakeDocumentRepository([document])
    uow = _FakeUnitOfWork(document_repo)
    use_case = DeleteDocumentUseCase(_as_uow(uow))

    await use_case(DeleteDocumentDTO(user_id=user_id, document_id=document.id))

    assert document_repo.deleted == [document.id]
    assert uow.committed is True


async def test_delete_document_use_case_raises_for_foreign_document() -> None:
    document = _make_document()
    document_repo = _FakeDocumentRepository([document])
    uow = _FakeUnitOfWork(document_repo)
    use_case = DeleteDocumentUseCase(_as_uow(uow))

    with pytest.raises(DocumentAccessDeniedException):
        await use_case(DeleteDocumentDTO(user_id=uuid.uuid4(), document_id=document.id))

    assert document_repo.deleted == []
    assert uow.committed is False
