import re
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import Boolean, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.kit.exceptions import (
    InvalidCreatedAtException,
    InvalidEmailException,
    InvalidPasswordException,
    InvalidUpdatedAtException,
    UserAlreadyInactiveException,
    UserInactiveException,
)
from src.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from src.models.chat import ChatSessionModel
    from src.models.collection import CollectionModel
    from src.models.document import DocumentModel
    from src.models.search_query import SearchQueryModel
    from src.models.tag import TagModel

_EMAIL_REGEX = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

class UserModel(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "users"
    
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(100))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    preferences: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    
    documents: Mapped[list["DocumentModel"]] = relationship(back_populates="user", passive_deletes=True)
    collections: Mapped[list["CollectionModel"]] = relationship(back_populates="user", passive_deletes=True)
    tags: Mapped[list["TagModel"]] = relationship(back_populates="user", passive_deletes=True)
    search_queries: Mapped[list["SearchQueryModel"]] = relationship(back_populates="user", passive_deletes=True)
    chat_sessions: Mapped[list["ChatSessionModel"]] = relationship(back_populates="user", passive_deletes=True)

    def __init__(self, **kwargs: object) -> None:
        if "email" in kwargs:
            kwargs["email"] = self._validate_email(str(kwargs["email"]))
        if "password" in kwargs:
            kwargs["hashed_password"] = kwargs.pop("password")
        if "hashed_password" in kwargs:
            kwargs["hashed_password"] = self._validate_hashed_password(str(kwargs["hashed_password"]))
        kwargs.setdefault("display_name", None)
        kwargs.setdefault("is_active", True)
        kwargs.setdefault("preferences", {})
        kwargs.setdefault("created_at", datetime.now(UTC))
        kwargs.setdefault("updated_at", None)
        super().__init__(**kwargs)
        self._validate_created_at(self.created_at)
        self._validate_updated_at(self.updated_at, self.created_at)

    @property
    def password(self) -> str:
        return self.hashed_password

    @classmethod
    def create(
        cls,
        *,
        id: UUID,
        email: str,
        password: str,
        display_name: str | None = None,
    ) -> "UserModel":
        return cls(id=id, email=email, password=password, display_name=display_name)

    def deactivate(self) -> None:
        if not self.is_active:
            raise UserAlreadyInactiveException("user already inactive")
        self.is_active = False
        self.updated_at = datetime.now(UTC)

    def update_display_name(self, display_name: str | None) -> None:
        if display_name != self.display_name:
            self.display_name = display_name
            self.updated_at = datetime.now(UTC)

    def update_email(self, email: str) -> None:
        normalized_email = self._validate_email(email)
        if normalized_email != self.email:
            self.email = normalized_email
            self.updated_at = datetime.now(UTC)

    def update_preferences(self, preferences: dict[str, object]) -> None:
        if preferences != self.preferences:
            self.preferences = dict(preferences)
            self.updated_at = datetime.now(UTC)

    def ensure_active(self) -> None:
        if not self.is_active:
            raise UserInactiveException("user inactive")

    def __repr__(self) -> str:
        return (
            f"UserModel(id={self.id}, email={self.email!r}, "
            f"display_name={self.display_name!r}, is_active={self.is_active})"
        )

    @staticmethod
    def _validate_email(email: str) -> str:
        if not _EMAIL_REGEX.match(email):
            raise InvalidEmailException("Invalid email")
        return email

    @staticmethod
    def _validate_hashed_password(password: str) -> str:
        if not password.strip():
            raise InvalidPasswordException("Password can't be empty")
        return password

    @staticmethod
    def _validate_created_at(created_at: datetime) -> None:
        if created_at.tzinfo is None:
            raise InvalidCreatedAtException("datetime must be timezone-aware")
        if created_at > datetime.now(UTC):
            raise InvalidCreatedAtException("created_at can't be in the future")

    @staticmethod
    def _validate_updated_at(updated_at: datetime | None, created_at: datetime) -> None:
        if updated_at is None:
            return
        if updated_at.tzinfo is None:
            raise InvalidUpdatedAtException("datetime must be timezone-aware")
        if updated_at > datetime.now(UTC):
            raise InvalidUpdatedAtException("updated_at can't be in the future")
        if updated_at < created_at:
            raise InvalidUpdatedAtException("updated_at can't be earlier than created_at")
