import uuid
from datetime import UTC, datetime, timedelta

import pytest

from src.domain.entities.user_entity import UserEntity
from src.domain.exceptions import (
    InvalidCreatedAtException,
    InvalidPasswordException,
    UserAlreadyInactiveException,
    UserInactiveException,
)
from src.domain.value_objects.email import Email


class TestEmail:
    def test_valid_email(self) -> None:
        email = Email(value="user@example.com")
        assert str(email) == "user@example.com"

    def test_valid_email_with_subdomain(self) -> None:
        email = Email(value="user@mail.example.com")
        assert email.value == "user@mail.example.com"

    def test_invalid_email_no_at(self) -> None:
        from src.domain.exceptions import InvalidEmailException
        with pytest.raises(InvalidEmailException):
            Email(value="userexample.com")

    def test_invalid_email_no_domain(self) -> None:
        from src.domain.exceptions import InvalidEmailException
        with pytest.raises(InvalidEmailException):
            Email(value="user@")

    def test_invalid_email_no_tld(self) -> None:
        from src.domain.exceptions import InvalidEmailException
        with pytest.raises(InvalidEmailException):
            Email(value="user@example")

    def test_invalid_email_spaces(self) -> None:
        from src.domain.exceptions import InvalidEmailException
        with pytest.raises(InvalidEmailException):
            Email(value="user @example.com")

    def test_email_is_frozen(self) -> None:
        email = Email(value="user@example.com")
        with pytest.raises(AttributeError):
            email.value = "other@example.com"  # type: ignore[misc]

    def test_email_equality(self) -> None:
        a = Email(value="user@example.com")
        b = Email(value="user@example.com")
        assert a == b

    def test_email_inequality(self) -> None:
        a = Email(value="user@example.com")
        b = Email(value="other@example.com")
        assert a != b


class TestUserEntity:
    @staticmethod
    def _make_user(**overrides) -> UserEntity:
        defaults = {
            "id": uuid.uuid4(),
            "email": Email(value="test@example.com"),
            "password": "$2b$12$hashedpasswordhere",
            "display_name": "Test User",
            "is_active": True,
            "created_at": datetime.now(UTC),
            "updated_at": None,
        }
        defaults.update(overrides)
        return UserEntity(**defaults)

    def test_create_factory(self) -> None:
        user = UserEntity.create(
            id=uuid.uuid4(),
            email=Email(value="new@example.com"),
            password="$2b$12$hashedpassword",
        )
        assert user.is_active is True
        assert user.updated_at is None
        assert user.display_name is None
        assert str(user.email) == "new@example.com"

    def test_create_with_display_name(self) -> None:
        user = UserEntity.create(
            id=uuid.uuid4(),
            email=Email(value="new@example.com"),
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
        new_email = Email(value="new@example.com")
        user.update_email(new_email)
        assert user.email == new_email
        assert user.updated_at is not None

    def test_update_email_same_value_no_update(self) -> None:
        email = Email(value="same@example.com")
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
        assert "UserEntity" in r
        assert "test@example.com" in r
