"""add_enrichment_fields

Revision ID: 4f8c2a6a91b8
Revises: 3f8c2a6a91b7
Create Date: 2026-05-01 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "4f8c2a6a91b8"
down_revision: str | Sequence[str] | None = "3f8c2a6a91b7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("documents", sa.Column("entities", postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column("documents", sa.Column("categories", postgresql.JSONB(astext_type=sa.Text()), nullable=True))


def downgrade() -> None:
    op.drop_column("documents", "categories")
    op.drop_column("documents", "entities")
