from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel


class AppearancePreferences(BaseModel):
    theme: Literal["dark"] = "dark"


class PrivacyPreferences(BaseModel):
    share_usage_data: bool = False
    retain_query_history: bool = True


class AIPreferences(BaseModel):
    answer_language: Literal["match_question", "english", "ukrainian"] = "match_question"
    retrieval_depth: Literal["focused", "balanced", "broad"] = "balanced"


class UserPreferencesResponse(BaseModel):
    appearance: AppearancePreferences = AppearancePreferences()
    privacy: PrivacyPreferences = PrivacyPreferences()
    ai: AIPreferences = AIPreferences()


class UserPreferencesUpdateRequest(BaseModel):
    appearance: AppearancePreferences = AppearancePreferences()
    privacy: PrivacyPreferences = PrivacyPreferences()
    ai: AIPreferences = AIPreferences()


class UserResponse(BaseModel):
    id: UUID
    email: str
    display_name: str | None
    is_active: bool
    preferences: UserPreferencesResponse = UserPreferencesResponse()
    created_at: datetime
    updated_at: datetime | None
