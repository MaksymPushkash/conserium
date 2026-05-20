import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import Date, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.infrastructure.database.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from src.infrastructure.database.models.user import UserModel


class LearningGoalModel(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "learning_goals"

    user_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    topic: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    target_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="active")

    user: Mapped["UserModel"] = relationship()


class LearningGoalResourceModel(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "learning_goal_resources"

    goal_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("learning_goals.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    area: Mapped[str] = mapped_column(String(160), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    search_query: Mapped[str] = mapped_column(String(300), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    url: Mapped[str | None] = mapped_column(Text)
    excerpt: Mapped[str | None] = mapped_column(Text)
    score: Mapped[float] = mapped_column(nullable=False)
    refreshed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)

    goal: Mapped[LearningGoalModel] = relationship()
