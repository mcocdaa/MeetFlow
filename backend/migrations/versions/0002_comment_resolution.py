"""add comment resolution state

Revision ID: 0002
Revises: 0001
Create Date: 2026-07-23 19:35:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0002"
down_revision: Union[str, Sequence[str], None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("comments", schema=None) as batch_op:
        batch_op.add_column(sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("resolved_by", sa.String(length=36), nullable=True))
        batch_op.create_foreign_key(
            "fk_comments_resolved_by_users", "users", ["resolved_by"], ["id"]
        )


def downgrade() -> None:
    with op.batch_alter_table("comments", schema=None) as batch_op:
        batch_op.drop_constraint("fk_comments_resolved_by_users", type_="foreignkey")
        batch_op.drop_column("resolved_by")
        batch_op.drop_column("resolved_at")
