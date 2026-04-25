from datetime import UTC, datetime
from uuid import UUID

from src.domain.exceptions import (
    InvalidCreatedAtException,
    InvalidPasswordException,
    InvalidUpdatedAtException,
    UserAlreadyInactiveException,
    UserInactiveException,
)
from src.domain.value_objects.email import Email


class UserEntity:
    def __init__(
        self,
        *,
        id: UUID,
        email: Email,
        password: str,
        display_name: str | None,
        is_active: bool,
        created_at: datetime,
        updated_at: datetime | None,
    ) -> None:
        
        self._id = id
        self._email = email
        self._password = self._validate_hashed_password(password)
        self._display_name = display_name
        self._is_active = is_active
        self._created_at = self._validate_created_at(created_at)
        self._updated_at = self._validate_updated_at(updated_at, created_at)


    @property
    def id(self) -> UUID:
        return self._id

    @property
    def email(self) -> Email:
        return self._email

    @property
    def password(self) -> str:
        return self._password

    @property
    def display_name(self) -> str | None:
        return self._display_name

    @property
    def is_active(self) -> bool:
        return self._is_active

    @property
    def created_at(self) -> datetime:
        return self._created_at

    @property
    def updated_at(self) -> datetime | None:
        return self._updated_at



    def deactivate(self) -> None:
        if not self._is_active:
            raise UserAlreadyInactiveException("user already inactive")
        self._is_active = False
        self._updated_at = datetime.now(UTC)

    def update_display_name(self, display_name: str | None) -> None:
        if display_name == self._display_name:
            return
        self._display_name = display_name
        self._updated_at = datetime.now(UTC)

    def update_email(self, email: Email) -> None:
        if email == self._email:
            return
        self._email = email
        self._updated_at = datetime.now(UTC)

    def ensure_active(self) -> None:
        if not self._is_active:
            raise UserInactiveException("user inactive")


    @classmethod
    def create(
        cls,
        id: UUID,
        email: Email,
        password: str,
        display_name: str | None = None,
    ) -> "UserEntity":
        return cls(
            id=id,
            email=email,
            password=password,
            display_name=display_name,
            is_active=True,
            created_at=datetime.now(UTC),
            updated_at=None,
        )


    def _validate_created_at(self, created_at: datetime) -> datetime:
        if created_at.tzinfo is None:
            raise InvalidCreatedAtException("datetime must be timezone-aware")
        if created_at > datetime.now(UTC):
            raise InvalidCreatedAtException("created_at can't be in the future")
        return created_at

    def _validate_updated_at(
        self, updated_at: datetime | None, created_at: datetime
    ) -> datetime | None:
        if updated_at is None:
            return None
        if updated_at.tzinfo is None:
            raise InvalidUpdatedAtException("datetime must be timezone-aware")
        if updated_at < created_at:
            raise InvalidUpdatedAtException("updated_at can't be before created_at")
        if updated_at > datetime.now(UTC):
            raise InvalidUpdatedAtException("updated_at can't be in the future")
        return updated_at
    
    def _validate_hashed_password(self, password: str) -> str:
        if not password.strip():
            raise InvalidPasswordException("Password can't be empty")
        return password
    

    def __repr__(self) -> str:
        return (
            f"UserEntity("
            f"id={self._id}, "
            f"email={self._email}, "
            f"display_name={self._display_name}, "
            f"is_active={self._is_active}"
            f")"
        )