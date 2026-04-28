"""make_updated_at_nullable

Revision ID: 3f8c2a6a91b7
Revises: 2bdb2bd9a1a6
Create Date: 2026-04-28 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "3f8c2a6a91b7"
down_revision: str | Sequence[str] | None = "2bdb2bd9a1a6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLES_WITH_UPDATED_AT = ("users", "collections", "tags", "documents")


def upgrade() -> None:
    """Allow updated_at to stay NULL until the first actual update."""
    for table_name in _TABLES_WITH_UPDATED_AT:
        op.alter_column(
            table_name,
            "updated_at",
            existing_type=sa.DateTime(timezone=True),
            server_default=None,
            nullable=True,
        )


def downgrade() -> None:
    """Restore the previous updated_at default/non-null semantics."""
    op.execute("UPDATE users SET updated_at = created_at WHERE updated_at IS NULL")
    op.execute("UPDATE collections SET updated_at = created_at WHERE updated_at IS NULL")
    op.execute("UPDATE tags SET updated_at = created_at WHERE updated_at IS NULL")
    op.execute("UPDATE documents SET updated_at = created_at WHERE updated_at IS NULL")

    for table_name in _TABLES_WITH_UPDATED_AT:
        op.alter_column(
            table_name,
            "updated_at",
            existing_type=sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        )
