from dataclasses import dataclass

from src.review.grade import ReviewGrade


@dataclass(frozen=True, slots=True)
class ReviewSchedule:
    interval_days: int
    ease_factor: float


def next_review_schedule(*, grade: ReviewGrade, interval_days: int, ease_factor: float) -> ReviewSchedule:
    if grade.value == "again":
        return ReviewSchedule(interval_days=1, ease_factor=max(1.3, ease_factor - 0.2))
    if grade.value == "hard":
        return ReviewSchedule(
            interval_days=max(2, int(max(1, interval_days) * 1.2)),
            ease_factor=max(1.3, ease_factor - 0.1),
        )
    if grade.value == "easy":
        return ReviewSchedule(
            interval_days=max(4, int(max(1, interval_days) * (ease_factor + 0.3))),
            ease_factor=min(3.2, ease_factor + 0.15),
        )
    return ReviewSchedule(interval_days=max(3, int(max(1, interval_days) * ease_factor)), ease_factor=ease_factor)
