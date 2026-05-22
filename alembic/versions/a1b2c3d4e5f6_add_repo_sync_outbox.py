"""add repo sync outbox"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "a1b2c3d4e5f6"
down_revision: str | Sequence[str] | None = "f9a1c3e5d7b2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "repo_syncs",
        sa.Column(
            "include_paths",
            sa.JSON(),
            server_default=sa.text("'[\"README.md\", \"docs/**/*.md\", \"**/*.md\"]'::json"),
            nullable=False,
        ),
    )
    op.add_column(
        "repo_syncs",
        sa.Column(
            "exclude_paths",
            sa.JSON(),
            server_default=sa.text("'[\"node_modules/**\", \".git/**\", \"dist/**\"]'::json"),
            nullable=False,
        ),
    )
    op.create_table(
        "repo_sync_outbox",
        sa.Column("repo_sync_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("task_name", sa.String(length=120), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("dispatched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["repo_sync_id"], ["repo_syncs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_repo_sync_outbox_document_id", "repo_sync_outbox", ["document_id"])
    op.create_index("ix_repo_sync_outbox_repo_sync_id", "repo_sync_outbox", ["repo_sync_id"])
    op.create_index("ix_repo_sync_outbox_status", "repo_sync_outbox", ["status"])
    op.create_index(
        "uq_repo_sync_outbox_active_task",
        "repo_sync_outbox",
        ["repo_sync_id", "document_id", "task_name"],
        unique=True,
        postgresql_where=sa.text("status != 'dispatched'"),
    )


def downgrade() -> None:
    op.drop_index("uq_repo_sync_outbox_active_task", table_name="repo_sync_outbox")
    op.drop_index("ix_repo_sync_outbox_status", table_name="repo_sync_outbox")
    op.drop_index("ix_repo_sync_outbox_repo_sync_id", table_name="repo_sync_outbox")
    op.drop_index("ix_repo_sync_outbox_document_id", table_name="repo_sync_outbox")
    op.drop_table("repo_sync_outbox")
    op.drop_column("repo_syncs", "exclude_paths")
    op.drop_column("repo_syncs", "include_paths")
