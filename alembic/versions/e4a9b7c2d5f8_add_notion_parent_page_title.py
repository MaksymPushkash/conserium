"""add notion parent page title

Revision ID: e4a9b7c2d5f8
Revises: d2f6a8c1b4e9
Create Date: 2026-05-18 17:10:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "e4a9b7c2d5f8"
down_revision: str | None = "d2f6a8c1b4e9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "external_connections",
        sa.Column("default_parent_page_title", sa.String(length=300), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("external_connections", "default_parent_page_title")
