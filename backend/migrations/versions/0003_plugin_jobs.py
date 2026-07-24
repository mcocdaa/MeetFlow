"""add persistent plugin jobs

Revision ID: 0003
Revises: 0002
Create Date: 2026-07-24 09:42:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0003"
down_revision: Union[str, Sequence[str], None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "plugin_jobs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("plugin_id", sa.String(length=120), nullable=False),
        sa.Column("action_id", sa.String(length=160), nullable=False),
        sa.Column("target_type", sa.String(length=40), nullable=False),
        sa.Column("target_id", sa.String(length=36), nullable=False),
        sa.Column("dedupe_key", sa.String(length=256), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("input_json", sa.JSON(), nullable=False),
        sa.Column("context_snapshot", sa.JSON(), nullable=False),
        sa.Column("result_json", sa.JSON(), nullable=True),
        sa.Column("error_code", sa.String(length=80), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("rerun_of_id", sa.String(length=36), sa.ForeignKey("plugin_jobs.id"), nullable=True),
        sa.Column("created_by", sa.String(length=36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_plugin_jobs_dedupe",
        "plugin_jobs",
        ["dedupe_key", "status"],
        unique=True,
        sqlite_where=sa.text("status IN ('queued', 'requesting')"),
    )
    for column in ("plugin_id", "action_id", "target_type", "target_id", "status", "rerun_of_id", "created_by", "created_at"):
        op.create_index(f"ix_plugin_jobs_{column}", "plugin_jobs", [column])


def downgrade() -> None:
    op.drop_table("plugin_jobs")
