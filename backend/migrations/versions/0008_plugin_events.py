"""add plugin event outbox

Revision ID: 0008
Revises: 0007
Create Date: 2026-07-31 17:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0008"
down_revision: Union[str, Sequence[str], None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "plugin_events",
        sa.Column("event_id", sa.String(length=256), primary_key=True),
        sa.Column("event_type", sa.String(length=120), nullable=False),
        sa.Column("payload_version", sa.Integer(), nullable=False),
        sa.Column("target_type", sa.String(length=40), nullable=False),
        sa.Column("target_id", sa.String(length=36), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    for column in ("event_type", "target_type", "target_id", "status", "next_attempt_at", "created_at"):
        op.create_index(f"ix_plugin_events_{column}", "plugin_events", [column])
    op.create_index(
        "ix_plugin_events_claim",
        "plugin_events",
        ["status", "next_attempt_at"],
    )


def downgrade() -> None:
    op.drop_table("plugin_events")
