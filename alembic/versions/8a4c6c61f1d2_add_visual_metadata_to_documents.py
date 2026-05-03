"""add visual metadata to documents

Revision ID: 8a4c6c61f1d2
Revises: 4f8c2a6a91b8
Create Date: 2026-05-01 18:05:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "8a4c6c61f1d2"
down_revision: str | Sequence[str] | None = "4f8c2a6a91b8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("documents", sa.Column("visual_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True))


def downgrade() -> None:
    op.drop_column("documents", "visual_metadata")
