from datetime import UTC, datetime


def activity_temperature(last_used_at: datetime, *, now: datetime | None = None) -> str:
    age_days = ((now or datetime.now(UTC)) - last_used_at).days
    if age_days >= 30:
        return "forgotten"
    if age_days >= 14:
        return "cold"
    return "hot"
