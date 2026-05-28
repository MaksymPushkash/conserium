"""add flashcards"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "k1l2m3n4o5p6"
down_revision: str | Sequence[str] | None = "j0k1l2m3n4o5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "flashcards",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("collection_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("source_document_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("source_chunk_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("scope_type", sa.String(length=32), nullable=False),
        sa.Column("topic", sa.String(length=120), nullable=True),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("answer", sa.Text(), nullable=False),
        sa.Column("citation_metadata", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("interval_days", sa.Integer(), nullable=False),
        sa.Column("ease_factor", sa.Float(), nullable=False),
        sa.Column("review_count", sa.Integer(), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["collection_id"], ["collections.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["source_chunk_id"], ["chunks.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["source_document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_flashcards_collection_id", "flashcards", ["collection_id"])
    op.create_index("ix_flashcards_due_at", "flashcards", ["due_at"])
    op.create_index("ix_flashcards_source_document_id", "flashcards", ["source_document_id"])
    op.create_index("ix_flashcards_user_due", "flashcards", ["user_id", "due_at"])
    op.create_index("ix_flashcards_user_document", "flashcards", ["user_id", "source_document_id"])
    op.create_index("ix_flashcards_user_id", "flashcards", ["user_id"])
    op.create_index("ix_flashcards_user_scope", "flashcards", ["user_id", "scope_type"])

    op.create_table(
        "flashcard_reviews",
        sa.Column("flashcard_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("grade", sa.String(length=16), nullable=False),
        sa.Column("previous_interval_days", sa.Integer(), nullable=False),
        sa.Column("next_interval_days", sa.Integer(), nullable=False),
        sa.Column("previous_ease_factor", sa.Float(), nullable=False),
        sa.Column("next_ease_factor", sa.Float(), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(["flashcard_id"], ["flashcards.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_flashcard_reviews_flashcard_id", "flashcard_reviews", ["flashcard_id"])
    op.create_index("ix_flashcard_reviews_flashcard_reviewed", "flashcard_reviews", ["flashcard_id", "reviewed_at"])
    op.create_index("ix_flashcard_reviews_user_id", "flashcard_reviews", ["user_id"])
    op.create_index("ix_flashcard_reviews_user_reviewed", "flashcard_reviews", ["user_id", "reviewed_at"])


def downgrade() -> None:
    op.drop_index("ix_flashcard_reviews_user_reviewed", table_name="flashcard_reviews")
    op.drop_index("ix_flashcard_reviews_user_id", table_name="flashcard_reviews")
    op.drop_index("ix_flashcard_reviews_flashcard_reviewed", table_name="flashcard_reviews")
    op.drop_index("ix_flashcard_reviews_flashcard_id", table_name="flashcard_reviews")
    op.drop_table("flashcard_reviews")
    op.drop_index("ix_flashcards_user_scope", table_name="flashcards")
    op.drop_index("ix_flashcards_user_id", table_name="flashcards")
    op.drop_index("ix_flashcards_user_document", table_name="flashcards")
    op.drop_index("ix_flashcards_user_due", table_name="flashcards")
    op.drop_index("ix_flashcards_source_document_id", table_name="flashcards")
    op.drop_index("ix_flashcards_due_at", table_name="flashcards")
    op.drop_index("ix_flashcards_collection_id", table_name="flashcards")
    op.drop_table("flashcards")
