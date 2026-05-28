from datetime import UTC, datetime
from typing import TYPE_CHECKING, cast
from uuid import UUID, uuid4

import pytest

from src.application.dtos.document_dtos import DocumentDTO
from src.application.dtos.external_intake_dtos import ExternalIngestDTO
from src.application.dtos.ingestion_dtos import IngestDocumentDTO
from src.application.ports.persistence.external_intake_repository import ExternalIntakeItemRecord
from src.application.use_cases.external_intake import IngestExternalItemUseCase
from src.domain.value_objects.document_status import DocumentStatus
from src.domain.value_objects.document_type import DocumentType

if TYPE_CHECKING:
    from src.application.ports.persistence.unit_of_work import IUnitOfWork
    from src.application.use_cases.documents.ingest_document_use_case import IngestDocumentUseCase


@pytest.mark.asyncio
async def test_external_intake_records_queued_document_and_idempotency() -> None:
    user_id = uuid4()
    api_key_id = uuid4()
    ingest_document = _FakeIngestDocument(user_id=user_id)
    uow = _ExternalIntakeUow()
    use_case = IngestExternalItemUseCase(cast("IUnitOfWork", uow), cast("IngestDocumentUseCase", ingest_document))

    first = await use_case(
        ExternalIngestDTO(
            user_id=user_id,
            api_key_id=api_key_id,
            provider="Webhook",
            external_id="message-1",
            title="Saved URL",
            type=DocumentType.URL,
            source_url="https://example.com",
            tags=["cloud", "cloud"],
        )
    )
    second = await use_case(
        ExternalIngestDTO(
            user_id=user_id,
            api_key_id=api_key_id,
            provider="webhook",
            external_id="message-1",
            title="Saved URL",
            type=DocumentType.URL,
            source_url="https://example.com",
        )
    )

    assert first.intake_item.status == "QUEUED"
    assert first.intake_item.document_id == ingest_document.document.id
    assert first.intake_item.tags == ["cloud"]
    assert ingest_document.calls[0].tags == ["cloud"]
    assert second.intake_item.id == first.intake_item.id
    assert len(ingest_document.calls) == 1


@pytest.mark.asyncio
async def test_external_intake_create_conflict_returns_existing_without_duplicate_document() -> None:
    user_id = uuid4()
    api_key_id = uuid4()
    existing_document_id = uuid4()
    now = datetime.now(UTC)
    existing = ExternalIntakeItemRecord(
        id=uuid4(),
        user_id=user_id,
        api_key_id=api_key_id,
        provider="webhook",
        external_id="message-1",
        idempotency_key="message-1",
        title="Saved URL",
        type=DocumentType.URL,
        collection_id=None,
        tags=[],
        source_url="https://example.com",
        raw_content=None,
        language=None,
        status="QUEUED",
        error_reason=None,
        document_id=existing_document_id,
        payload_metadata={},
        created_at=now,
    )
    ingest_document = _FakeIngestDocument(user_id=user_id)
    uow = _ExternalIntakeUow()
    uow.external_intake_repo.create_conflict_record = existing
    use_case = IngestExternalItemUseCase(cast("IUnitOfWork", uow), cast("IngestDocumentUseCase", ingest_document))

    result = await use_case(
        ExternalIngestDTO(
            user_id=user_id,
            api_key_id=api_key_id,
            provider="webhook",
            external_id="message-1",
            title="Saved URL",
            type=DocumentType.URL,
            source_url="https://example.com",
        )
    )

    assert result.intake_item.id == existing.id
    assert result.intake_item.document_id == existing_document_id
    assert len(ingest_document.calls) == 0


@pytest.mark.asyncio
async def test_external_intake_marks_failure_when_ingestion_fails() -> None:
    user_id = uuid4()
    api_key_id = uuid4()
    ingest_document = _FailingIngestDocument()
    uow = _ExternalIntakeUow()
    use_case = IngestExternalItemUseCase(cast("IUnitOfWork", uow), cast("IngestDocumentUseCase", ingest_document))

    with pytest.raises(RuntimeError, match="GitHub rate limited"):
        await use_case(
            ExternalIngestDTO(
                user_id=user_id,
                api_key_id=api_key_id,
                provider="telegram",
                external_id="message-2",
                title="Saved text",
                type=DocumentType.TEXT,
                raw_content="hello",
            )
        )

    assert uow.external_intake_repo.records[0].status == "FAILED"
    assert uow.external_intake_repo.records[0].error_reason == "GitHub rate limited"


class _ExternalIntakeUow:
    def __init__(self) -> None:
        self.external_intake_repo = _ExternalIntakeRepo()
        self.document_repo = _DocumentRepo()
        self.commits = 0

    async def __aenter__(self) -> "_ExternalIntakeUow":
        return self

    async def __aexit__(self, *args: object) -> None:
        return None

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        return None


class _ExternalIntakeRepo:
    def __init__(self) -> None:
        self.records: list[ExternalIntakeItemRecord] = []
        self.create_conflict_record: ExternalIntakeItemRecord | None = None

    async def create(self, record: ExternalIntakeItemRecord) -> ExternalIntakeItemRecord:
        if self.create_conflict_record is not None:
            return self.create_conflict_record
        self.records.append(record)
        return record

    async def get_by_idempotency_key(
        self,
        *,
        user_id: UUID,
        provider: str,
        idempotency_key: str,
    ) -> ExternalIntakeItemRecord | None:
        return next(
            (
                record
                for record in self.records
                if record.user_id == user_id and record.provider == provider and record.idempotency_key == idempotency_key
            ),
            None,
        )

    async def mark_queued(self, *, intake_item_id: UUID, document_id: UUID) -> ExternalIntakeItemRecord:
        record = self._record(intake_item_id)
        record.status = "QUEUED"
        record.document_id = document_id
        return record

    async def mark_failed(self, *, intake_item_id: UUID, error_reason: str) -> ExternalIntakeItemRecord:
        record = self._record(intake_item_id)
        record.status = "FAILED"
        record.error_reason = error_reason
        return record

    def _record(self, intake_item_id: UUID) -> ExternalIntakeItemRecord:
        return next(record for record in self.records if record.id == intake_item_id)


class _DocumentRepo:
    async def get_by_id(self, document_id: UUID) -> None:
        return None


class _FakeIngestDocument:
    def __init__(self, *, user_id: UUID) -> None:
        self.calls: list[IngestDocumentDTO] = []
        self.document = _document(user_id=user_id)

    async def __call__(self, dto: IngestDocumentDTO) -> DocumentDTO:
        self.calls.append(dto)
        return self.document


class _FailingIngestDocument:
    async def __call__(self, dto: IngestDocumentDTO) -> DocumentDTO:
        raise RuntimeError("GitHub rate limited")


def _document(*, user_id: UUID) -> DocumentDTO:
    now = datetime.now(UTC)
    return DocumentDTO(
        id=uuid4(),
        user_id=user_id,
        collection_id=None,
        title="Saved URL",
        type=DocumentType.URL,
        status=DocumentStatus.QUEUED,
        source_url="https://example.com",
        file_path=None,
        file_size_bytes=None,
        raw_content=None,
        summary=None,
        word_count=None,
        language=None,
        entities=None,
        categories=None,
        is_duplicate=False,
        duplicate_of_id=None,
        created_at=now,
        updated_at=None,
    )
