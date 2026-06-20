from datetime import datetime
from typing import Literal
from uuid import UUID

from src.kit.schemas import Schema


class AppearancePreferences(Schema):
    theme: Literal["dark", "light"] = "dark"


class PrivacyPreferences(Schema):
    share_usage_data: bool = False
    retain_query_history: bool = True


class AIPreferences(Schema):
    answer_language: Literal["match_question", "english", "ukrainian"] = "match_question"
    retrieval_depth: Literal["focused", "balanced", "broad"] = "balanced"


class UserPreferencesResponse(Schema):
    appearance: AppearancePreferences = AppearancePreferences()
    privacy: PrivacyPreferences = PrivacyPreferences()
    ai: AIPreferences = AIPreferences()


class UserPreferencesUpdateRequest(Schema):
    appearance: AppearancePreferences = AppearancePreferences()
    privacy: PrivacyPreferences = PrivacyPreferences()
    ai: AIPreferences = AIPreferences()


class UserResponse(Schema):
    id: UUID
    email: str
    display_name: str | None
    is_active: bool
    preferences: UserPreferencesResponse = UserPreferencesResponse()
    created_at: datetime
    updated_at: datetime | None


__all__ = [
    "AIPreferences",
    "AppearancePreferences",
    "PrivacyPreferences",
    "UserPreferencesResponse",
    "UserPreferencesUpdateRequest",
    "UserResponse",
]
