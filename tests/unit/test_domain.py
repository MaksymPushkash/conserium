import uuid
from datetime import UTC, datetime, timedelta
from typing import cast

import pytest

from src.documents.status import DocumentStatus
from src.documents.types import DocumentType
from src.kit.exceptions import (
    InvalidCreatedAtException,
    InvalidPasswordException,
    UserAlreadyInactiveException,
    UserInactiveException,
)
from src.models.chunk import ChunkModel
from src.models.document import DocumentModel
from src.models.user import UserModel


class TestEmail:
    def test_valid_email(self) -> None:
        user = TestUserModel._make_user(email="user@example.com")
        assert user.email == "user@example.com"

    def test_valid_email_with_subdomain(self) -> None:
        user = TestUserModel._make_user(email="user@mail.example.com")
        assert user.email == "user@mail.example.com"

    def test_invalid_email_no_at(self) -> None:
        from src.kit.exceptions import InvalidEmailException

        with pytest.raises(InvalidEmailException):
            TestUserModel._make_user(email="userexample.com")

    def test_invalid_email_no_domain(self) -> None:
        from src.kit.exceptions import InvalidEmailException

        with pytest.raises(InvalidEmailException):
            TestUserModel._make_user(email="user@")

    def test_invalid_email_no_tld(self) -> None:
        from src.kit.exceptions import InvalidEmailException

        with pytest.raises(InvalidEmailException):
            TestUserModel._make_user(email="user@example")

    def test_invalid_email_spaces(self) -> None:
        from src.kit.exceptions import InvalidEmailException

        with pytest.raises(InvalidEmailException):
            TestUserModel._make_user(email="user @example.com")

    def test_email_equality(self) -> None:
        a = "user@example.com"
        b = "user@example.com"
        assert a == b

    def test_email_inequality(self) -> None:
        a = "user@example.com"
        b = "other@example.com"
        assert a != b


class TestUserModel:
    @staticmethod
    def _make_user(**overrides: object) -> UserModel:
        defaults: dict[str, object] = {
            "id": uuid.uuid4(),
            "email": "test@example.com",
            "password": "$2b$12$hashedpasswordhere",
            "display_name": "Test User",
            "is_active": True,
            "created_at": datetime.now(UTC),
            "updated_at": None,
        }
        defaults.update(overrides)
        return UserModel(
            id=cast("uuid.UUID", defaults["id"]),
            email=cast("str", defaults["email"]),
            password=cast("str", defaults["password"]),
            display_name=cast("str | None", defaults["display_name"]),
            is_active=cast("bool", defaults["is_active"]),
            created_at=cast("datetime", defaults["created_at"]),
            updated_at=cast("datetime | None", defaults["updated_at"]),
        )

    def test_create_factory(self) -> None:
        user = UserModel.create(
            id=uuid.uuid4(),
            email="new@example.com",
            password="$2b$12$hashedpassword",
        )
        assert user.is_active is True
        assert user.updated_at is None
        assert user.display_name is None
        assert str(user.email) == "new@example.com"

    def test_create_with_display_name(self) -> None:
        user = UserModel.create(
            id=uuid.uuid4(),
            email="new@example.com",
            password="$2b$12$hashedpassword",
            display_name="My Name",
        )
        assert user.display_name == "My Name"

    def test_deactivate(self) -> None:
        user = self._make_user()
        assert user.is_active is True
        user.deactivate()
        assert user.is_active is False
        assert user.updated_at is not None

    def test_deactivate_already_inactive_raises(self) -> None:
        user = self._make_user(is_active=False)
        with pytest.raises(UserAlreadyInactiveException):
            user.deactivate()

    def test_ensure_active_when_active(self) -> None:
        user = self._make_user(is_active=True)
        user.ensure_active()  # should not raise

    def test_ensure_active_when_inactive_raises(self) -> None:
        user = self._make_user(is_active=False)
        with pytest.raises(UserInactiveException):
            user.ensure_active()

    def test_update_display_name(self) -> None:
        user = self._make_user(display_name="Old")
        user.update_display_name("New")
        assert user.display_name == "New"
        assert user.updated_at is not None

    def test_update_display_name_same_value_no_update(self) -> None:
        user = self._make_user(display_name="Same")
        user.update_display_name("Same")
        assert user.updated_at is None  # no change, no timestamp

    def test_update_email(self) -> None:
        user = self._make_user()
        new_email = "new@example.com"
        user.update_email(new_email)
        assert user.email == new_email
        assert user.updated_at is not None

    def test_update_email_same_value_no_update(self) -> None:
        email = "same@example.com"
        user = self._make_user(email=email)
        user.update_email(email)
        assert user.updated_at is None

    def test_empty_password_raises(self) -> None:
        with pytest.raises(InvalidPasswordException):
            self._make_user(password="   ")

    def test_created_at_naive_datetime_raises(self) -> None:
        with pytest.raises(InvalidCreatedAtException):
            self._make_user(created_at=datetime.now())

    def test_created_at_in_future_raises(self) -> None:
        with pytest.raises(InvalidCreatedAtException):
            self._make_user(created_at=datetime.now(UTC) + timedelta(hours=1))

    def test_repr(self) -> None:
        user = self._make_user()
        r = repr(user)
        assert "UserModel" in r
        assert "test@example.com" in r


class TestDocumentModel:
    @staticmethod
    def _embedding() -> list[float]:
        return [0.1] * DocumentModel.EMBEDDING_DIMENSIONS

    @staticmethod
    def _make_document(**overrides: object) -> DocumentModel:
        defaults: dict[str, object] = {
            "id": uuid.uuid4(),
            "user_id": uuid.uuid4(),
            "collection_id": None,
            "title": "Design Doc",
            "type": DocumentType.TEXT,
            "status": DocumentStatus.PENDING,
            "source_url": None,
            "file_path": None,
            "file_size_bytes": None,
            "raw_content": "Important content",
            "summary": None,
            "word_count": 2,
            "language": "en",
            "doc_embedding": None,
            "is_duplicate": False,
            "duplicate_of_id": None,
            "created_at": datetime.now(UTC),
            "updated_at": None,
        }
        defaults.update(overrides)
        return DocumentModel(
            id=cast("uuid.UUID", defaults["id"]),
            user_id=cast("uuid.UUID", defaults["user_id"]),
            collection_id=cast("uuid.UUID | None", defaults["collection_id"]),
            title=cast("str", defaults["title"]),
            type=cast("DocumentType", defaults["type"]),
            status=cast("DocumentStatus", defaults["status"]),
            source_url=cast("str | None", defaults["source_url"]),
            file_path=cast("str | None", defaults["file_path"]),
            file_size_bytes=cast("int | None", defaults["file_size_bytes"]),
            raw_content=cast("str | None", defaults["raw_content"]),
            summary=cast("str | None", defaults["summary"]),
            word_count=cast("int | None", defaults["word_count"]),
            language=cast("str | None", defaults["language"]),
            doc_embedding=cast("list[float] | None", defaults["doc_embedding"]),
            is_duplicate=cast("bool", defaults["is_duplicate"]),
            duplicate_of_id=cast("uuid.UUID | None", defaults["duplicate_of_id"]),
            created_at=cast("datetime", defaults["created_at"]),
            updated_at=cast("datetime | None", defaults["updated_at"]),
        )

    def test_create_factory_defaults_to_pending(self) -> None:
        document = DocumentModel.create(
            id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            title="Notes",
            type=DocumentType.MARKDOWN,
            raw_content="hello",
        )
        assert document.status == DocumentStatus.PENDING
        assert document.is_duplicate is False
        assert document.created_at.tzinfo is not None
        assert document.updated_at is None

    def test_lifecycle_status_transitions_touch_updated_at(self) -> None:
        queued_document = self._make_document()
        queued_document.mark_queued()
        assert queued_document.status == DocumentStatus.QUEUED
        assert queued_document.updated_at is not None

        processing_document = self._make_document()
        processing_document.mark_processing()
        assert processing_document.status == DocumentStatus.PROCESSING

        ready_document = self._make_document()
        ready_document.mark_ready()
        assert ready_document.status == DocumentStatus.READY

        failed_document = self._make_document()
        failed_document.mark_failed()
        assert failed_document.status == DocumentStatus.FAILED

    def test_empty_title_raises(self) -> None:
        with pytest.raises(ValueError):
            self._make_document(title="   ")

    def test_blank_raw_content_when_provided_raises(self) -> None:
        with pytest.raises(ValueError):
            self._make_document(raw_content="   ")

    def test_negative_file_size_raises(self) -> None:
        with pytest.raises(ValueError):
            self._make_document(file_size_bytes=-1)

    def test_invalid_document_embedding_dimension_raises(self) -> None:
        with pytest.raises(ValueError):
            self._make_document(doc_embedding=[0.1, 0.2])

    def test_document_embedding_is_available(self) -> None:
        document = self._make_document(doc_embedding=self._embedding())
        assert document.doc_embedding is not None
        assert document.doc_embedding[0] == 0.1

    def test_naive_created_at_raises(self) -> None:
        with pytest.raises(ValueError):
            self._make_document(created_at=datetime.now())

    def test_duplicate_requires_original_document_id(self) -> None:
        with pytest.raises(ValueError):
            self._make_document(is_duplicate=True, duplicate_of_id=None)

    def test_mark_duplicate_rejects_self_reference(self) -> None:
        document_id = uuid.uuid4()
        document = self._make_document(id=document_id)
        with pytest.raises(ValueError):
            document.mark_duplicate(document_id)

    def test_mark_duplicate_and_clear_duplicate(self) -> None:
        document = self._make_document()
        original_id = uuid.uuid4()
        document.mark_duplicate(original_id)
        assert document.is_duplicate is True
        assert document.duplicate_of_id == original_id

        document.clear_duplicate()
        assert document.is_duplicate is False
        assert document.duplicate_of_id is None


class TestChunkModel:
    @staticmethod
    def _embedding() -> list[float]:
        return [0.2] * ChunkModel.EMBEDDING_DIMENSIONS

    @staticmethod
    def _make_chunk(**overrides: object) -> ChunkModel:
        defaults: dict[str, object] = {
            "id": uuid.uuid4(),
            "document_id": uuid.uuid4(),
            "content": "Chunk content",
            "embedding": TestChunkModel._embedding(),
            "chunk_index": 0,
            "start_char": 0,
            "end_char": 13,
            "page_number": 1,
            "token_count": 2,
            "created_at": datetime.now(UTC),
        }
        defaults.update(overrides)
        return ChunkModel(
            id=cast("uuid.UUID", defaults["id"]),
            document_id=cast("uuid.UUID", defaults["document_id"]),
            content=cast("str", defaults["content"]),
            embedding=cast("list[float]", defaults["embedding"]),
            chunk_index=cast("int", defaults["chunk_index"]),
            start_char=cast("int | None", defaults["start_char"]),
            end_char=cast("int | None", defaults["end_char"]),
            page_number=cast("int | None", defaults["page_number"]),
            token_count=cast("int | None", defaults["token_count"]),
            created_at=cast("datetime", defaults["created_at"]),
        )

    def test_create_factory(self) -> None:
        chunk = ChunkModel.create(
            id=uuid.uuid4(),
            document_id=uuid.uuid4(),
            content="hello",
            embedding=self._embedding(),
            chunk_index=1,
        )
        assert chunk.content == "hello"
        assert chunk.chunk_index == 1
        assert chunk.created_at.tzinfo is not None

    def test_empty_content_raises(self) -> None:
        with pytest.raises(ValueError):
            self._make_chunk(content="   ")

    def test_invalid_embedding_dimension_raises(self) -> None:
        with pytest.raises(ValueError):
            self._make_chunk(embedding=[0.1])

    def test_embedding_is_available(self) -> None:
        chunk = self._make_chunk()
        assert chunk.embedding[0] == 0.2

    def test_negative_chunk_index_raises(self) -> None:
        with pytest.raises(ValueError):
            self._make_chunk(chunk_index=-1)

    def test_negative_metadata_raises(self) -> None:
        with pytest.raises(ValueError):
            self._make_chunk(token_count=-1)

    def test_invalid_char_range_raises(self) -> None:
        with pytest.raises(ValueError):
            self._make_chunk(start_char=10, end_char=1)

    def test_naive_created_at_raises(self) -> None:
        with pytest.raises(ValueError):
            self._make_chunk(created_at=datetime.now())

    def test_update_embedding(self) -> None:
        chunk = self._make_chunk()
        new_embedding = [0.4] * ChunkModel.EMBEDDING_DIMENSIONS
        chunk.update_embedding(new_embedding)
        assert chunk.embedding[0] == 0.4
