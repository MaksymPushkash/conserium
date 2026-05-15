"""add suggested questions to documents"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "c6d1a3f52e7b"
down_revision: str | Sequence[str] | None = "b2a7f39d4c20"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "documents",
        sa.Column("suggested_questions", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"),
    )
    op.execute(
        """
        UPDATE documents
        SET suggested_questions = visual_metadata -> 'suggested_questions'
        WHERE visual_metadata ? 'suggested_questions'
          AND jsonb_typeof(visual_metadata -> 'suggested_questions') = 'array'
        """
    )
    op.alter_column("documents", "suggested_questions", server_default=None)


def downgrade() -> None:
    op.drop_column("documents", "suggested_questions")
