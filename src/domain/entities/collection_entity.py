from datetime import UTC, datetime
from uuid import UUID


class CollectionEntity:
    def __init__(
        self,
        *,
        id: UUID,
        user_id: UUID,
        name: str,
        description: str | None,
        color: str | None,
        created_at: datetime,
        updated_at: datetime | None,
    ) -> None:
        self._id = id
        self._user_id = user_id
        self._name = self._validate_name(name)
        self._description = self._validate_optional_text(description, "description", max_length=2000)
        self._color = self._validate_color(color)
        self._created_at = created_at
        self._updated_at = updated_at

    @property
    def id(self) -> UUID:
        return self._id

    @property
    def user_id(self) -> UUID:
        return self._user_id

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str | None:
        return self._description

    @property
    def color(self) -> str | None:
        return self._color

    @property
    def created_at(self) -> datetime:
        return self._created_at

    @property
    def updated_at(self) -> datetime | None:
        return self._updated_at

    @classmethod
    def create(
        cls,
        *,
        id: UUID,
        user_id: UUID,
        name: str,
        description: str | None = None,
        color: str | None = None,
    ) -> "CollectionEntity":
        return cls(
            id=id,
            user_id=user_id,
            name=name,
            description=description,
            color=color,
            created_at=datetime.now(UTC),
            updated_at=None,
        )

    def update(self, *, name: str, description: str | None, color: str | None) -> None:
        next_name = self._validate_name(name)
        next_description = self._validate_optional_text(description, "description", max_length=2000)
        next_color = self._validate_color(color)
        if next_name == self._name and next_description == self._description and next_color == self._color:
            return
        self._name = next_name
        self._description = next_description
        self._color = next_color
        self._updated_at = datetime.now(UTC)

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
