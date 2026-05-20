"""add notion connection settings

Revision ID: b0e5c7d9a3f1
Revises: a9d4e6f8b2c1
Create Date: 2026-05-18 00:20:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "b0e5c7d9a3f1"
down_revision: str | None = "a9d4e6f8b2c1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("external_connections", sa.Column("default_parent_page_id", sa.String(length=120), nullable=True))


def downgrade() -> None:
    op.drop_column("external_connections", "default_parent_page_id")
