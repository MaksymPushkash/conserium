"""add note versions

Revision ID: b2a7f39d4c20
Revises: 9e52b6a2f4c1
Create Date: 2026-05-13 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "b2a7f39d4c20"
down_revision: str | Sequence[str] | None = "9e52b6a2f4c1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "note_versions",
        sa.Column("note_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=120), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(["note_id"], ["documents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_note_versions_note_created", "note_versions", ["note_id", "created_at"])
    op.create_index("ix_note_versions_user_note", "note_versions", ["user_id", "note_id"])


def downgrade() -> None:
    op.drop_index("ix_note_versions_user_note", table_name="note_versions")
    op.drop_index("ix_note_versions_note_created", table_name="note_versions")
    op.drop_table("note_versions")
