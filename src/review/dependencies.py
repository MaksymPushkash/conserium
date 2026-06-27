from __future__ import annotations

from fastapi import Depends

from src.postgres import AsyncSession, get_db_session
from src.review.service import ReviewService


def get_review_service(session: AsyncSession = Depends(get_db_session)) -> ReviewService:
    return ReviewService(session)


__all__ = ["get_review_service"]
