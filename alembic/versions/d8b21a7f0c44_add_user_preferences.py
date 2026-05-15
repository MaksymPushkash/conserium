"""add user preferences"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "d8b21a7f0c44"
down_revision: str | Sequence[str] | None = "c6d1a3f52e7b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("preferences", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
    )
    op.alter_column("users", "preferences", server_default=None)


def downgrade() -> None:
    op.drop_column("users", "preferences")
