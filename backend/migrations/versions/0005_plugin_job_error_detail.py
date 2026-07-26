"""persist safe plugin job error details

Revision ID: 0005
Revises: 0004
Create Date: 2026-07-26 12:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0005"
down_revision: Union[str, Sequence[str], None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("plugin_jobs") as batch_op:
        batch_op.add_column(sa.Column("error_detail", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("plugin_jobs") as batch_op:
        batch_op.drop_column("error_detail")
