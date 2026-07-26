"""persist plugin job draft dismissal

Revision ID: 0004
Revises: 0003
Create Date: 2026-07-26 10:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0004"
down_revision: Union[str, Sequence[str], None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("plugin_jobs") as batch_op:
        batch_op.add_column(sa.Column("dismissed_by", sa.String(length=36), nullable=True))
        batch_op.add_column(sa.Column("dismissed_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.create_foreign_key(
            "fk_plugin_jobs_dismissed_by_users", "users", ["dismissed_by"], ["id"]
        )


def downgrade() -> None:
    with op.batch_alter_table("plugin_jobs") as batch_op:
        batch_op.drop_constraint("fk_plugin_jobs_dismissed_by_users", type_="foreignkey")
        batch_op.drop_column("dismissed_at")
        batch_op.drop_column("dismissed_by")
