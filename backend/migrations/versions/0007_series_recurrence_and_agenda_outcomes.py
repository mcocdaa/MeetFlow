"""persist series recurrence and agenda outcome source fields

Revision ID: 0007
Revises: 0006
Create Date: 2026-07-30 12:45:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from app.domain.enums import OccurrenceKind, RecurrenceFrequency


revision: str = "0007"
down_revision: Union[str, Sequence[str], None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("meeting_series") as batch_op:
        batch_op.add_column(
            sa.Column(
                "recurrence_frequency",
                sa.Enum(RecurrenceFrequency, name="recurrencefrequency"),
                nullable=True,
            )
        )
        batch_op.add_column(sa.Column("recurrence_interval", sa.Integer(), nullable=False, server_default="1"))
        batch_op.add_column(sa.Column("recurrence_weekday", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("recurrence_month_day", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("recurrence_month", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("recurrence_local_time", sa.Time(), nullable=True))
        batch_op.add_column(sa.Column("recurrence_timezone", sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column("recurrence_anchor_date", sa.Date(), nullable=True))
        batch_op.alter_column("recurrence_interval", server_default=None)

    with op.batch_alter_table("meetings") as batch_op:
        batch_op.add_column(
            sa.Column(
                "occurrence_kind",
                sa.Enum(OccurrenceKind, name="occurrencekind"),
                nullable=False,
                server_default="manual",
            )
        )
        batch_op.add_column(sa.Column("series_slot_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.create_unique_constraint("uq_meeting_series_slot", ["series_id", "series_slot_at"])
        batch_op.alter_column("occurrence_kind", server_default=None)

    with op.batch_alter_table("agenda_items") as batch_op:
        batch_op.add_column(sa.Column("actual_duration_seconds", sa.Integer(), nullable=True))

    for table, unique_name, foreign_name in (
        ("decisions", "uq_decision_agenda_source_tag", "fk_decisions_source_agenda"),
        ("action_items", "uq_action_agenda_source_tag", "fk_action_items_source_agenda"),
        ("open_questions", "uq_question_agenda_source_tag", "fk_open_questions_source_agenda"),
    ):
        with op.batch_alter_table(table) as batch_op:
            batch_op.add_column(sa.Column("source_agenda_item_id", sa.String(), nullable=True))
            batch_op.add_column(sa.Column("source_tag_key", sa.String(length=64), nullable=True))
            batch_op.create_index(f"ix_{table}_source_agenda_item_id", ["source_agenda_item_id"])
            batch_op.create_foreign_key(foreign_name, "agenda_items", ["source_agenda_item_id"], ["id"], ondelete="CASCADE")
            batch_op.create_unique_constraint(unique_name, ["source_agenda_item_id", "source_tag_key"])


def downgrade() -> None:
    for table, unique_name, foreign_name in reversed((
        ("decisions", "uq_decision_agenda_source_tag", "fk_decisions_source_agenda"),
        ("action_items", "uq_action_agenda_source_tag", "fk_action_items_source_agenda"),
        ("open_questions", "uq_question_agenda_source_tag", "fk_open_questions_source_agenda"),
    )):
        with op.batch_alter_table(table) as batch_op:
            batch_op.drop_constraint(unique_name, type_="unique")
            batch_op.drop_constraint(foreign_name, type_="foreignkey")
            batch_op.drop_index(f"ix_{table}_source_agenda_item_id")
            batch_op.drop_column("source_tag_key")
            batch_op.drop_column("source_agenda_item_id")

    with op.batch_alter_table("agenda_items") as batch_op:
        batch_op.drop_column("actual_duration_seconds")

    with op.batch_alter_table("meetings") as batch_op:
        batch_op.drop_constraint("uq_meeting_series_slot", type_="unique")
        batch_op.drop_column("series_slot_at")
        batch_op.drop_column("occurrence_kind")

    with op.batch_alter_table("meeting_series") as batch_op:
        batch_op.drop_column("recurrence_anchor_date")
        batch_op.drop_column("recurrence_timezone")
        batch_op.drop_column("recurrence_local_time")
        batch_op.drop_column("recurrence_month")
        batch_op.drop_column("recurrence_month_day")
        batch_op.drop_column("recurrence_weekday")
        batch_op.drop_column("recurrence_interval")
        batch_op.drop_column("recurrence_frequency")
