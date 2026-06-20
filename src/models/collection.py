import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from src.models.document import DocumentModel
    from src.models.shared_workspace import WorkspaceModel
    from src.models.user import UserModel


class CollectionModel(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "collections"
    __table_args__ = (
        UniqueConstraint("user_id", "name", name="uq_collection_user_name"),
    )
    
    user_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    workspace_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="SET NULL"), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    color: Mapped[str | None] = mapped_column(String(7))
    
    user: Mapped["UserModel"] = relationship(back_populates="collections")
    workspace: Mapped["WorkspaceModel | None"] = relationship()
    documents: Mapped[list["DocumentModel"]] = relationship(back_populates="collection", passive_deletes=True)

    @classmethod
    def create(
        cls,
        *,
        id: uuid.UUID,
        user_id: uuid.UUID,
        name: str,
        workspace_id: uuid.UUID | None = None,
        description: str | None = None,
        color: str | None = None,
    ) -> "CollectionModel":
        return cls(
            id=id,
            user_id=user_id,
            workspace_id=workspace_id,
            name=cls._validate_name(name),
            description=cls._validate_optional_text(description, "description", max_length=2000),
            color=cls._validate_color(color),
            created_at=datetime.now(UTC),
            updated_at=None,
        )

    def update_details(self, *, name: str, description: str | None, color: str | None) -> None:
        next_name = self._validate_name(name)
        next_description = self._validate_optional_text(description, "description", max_length=2000)
        next_color = self._validate_color(color)
        if next_name == self.name and next_description == self.description and next_color == self.color:
            return
        self.name = next_name
        self.description = next_description
        self.color = next_color
        self.updated_at = datetime.now(UTC)

    @staticmethod
    def _validate_name(value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("collection name cannot be empty")
        if len(normalized) > 200:
            raise ValueError("collection name cannot exceed 200 characters")
        return normalized

    @staticmethod
    def _validate_optional_text(value: str | None, field: str, *, max_length: int) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            return None
        if len(normalized) > max_length:
            raise ValueError(f"{field} cannot exceed {max_length} characters")
        return normalized

    @staticmethod
    def _validate_color(value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            return None
        if len(normalized) != 7 or not normalized.startswith("#"):
            raise ValueError("collection color must be a #RRGGBB value")
        int(normalized[1:], 16)
        return normalized
