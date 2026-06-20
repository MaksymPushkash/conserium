from dataclasses import dataclass

from src.kit.exceptions import ValidationException


@dataclass(frozen=True, slots=True)
class ReviewGrade:
    value: str

    @classmethod
    def from_raw(cls, value: str) -> "ReviewGrade":
        normalized = value.strip().lower()
        if normalized not in {"again", "hard", "good", "easy"}:
            raise ValidationException("invalid review grade")
        return cls(value=normalized)
