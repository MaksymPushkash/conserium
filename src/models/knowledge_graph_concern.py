import uuid

from sqlalchemy import ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class KnowledgeGraphConcernModel(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "knowledge_graph_concerns"
    __table_args__ = (
        Index("ix_knowledge_graph_concerns_user_status", "user_id", "status"),
        Index("ix_knowledge_graph_concerns_node", "user_id", "node_id"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    node_id: Mapped[str | None] = mapped_column(String(240), nullable=True)
    node_kind: Mapped[str | None] = mapped_column(String(40), nullable=True)
    node_label: Mapped[str | None] = mapped_column(String(240), nullable=True)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="open")
