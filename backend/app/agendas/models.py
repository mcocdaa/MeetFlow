import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import (
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.auth.models import User
from app.database import Base
from app.domain.enums import AgendaStatus, AgendaType

if TYPE_CHECKING:
    from app.meetings.models import Meeting


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class AgendaItem(Base):
    __tablename__ = "agenda_items"
    __table_args__ = (
        UniqueConstraint(
            "meeting_id",
            "copied_from_agenda_item_id",
            name="uq_agenda_copy_per_meeting",
        ),
    )

    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    meeting_id: Mapped[str] = mapped_column(
        ForeignKey("meetings.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(300))
    agenda_type: Mapped[AgendaType] = mapped_column(
        Enum(AgendaType), default=AgendaType.discussion
    )
    proposer_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    presenter_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    estimated_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    actual_duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    notes_markdown: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[AgendaStatus] = mapped_column(
        Enum(AgendaStatus), default=AgendaStatus.planned, index=True
    )
    position: Mapped[int] = mapped_column(Integer)
    carry_from_open_question_id: Mapped[str | None] = mapped_column(
        ForeignKey(
            "open_questions.id",
            use_alter=True,
            name="fk_agenda_carry_open_question",
            ondelete="SET NULL",
        ),
        nullable=True,
        index=True,
    )
    copied_from_agenda_item_id: Mapped[str | None] = mapped_column(
        ForeignKey(
            "agenda_items.id",
            use_alter=True,
            name="fk_agenda_copied_from_agenda",
            ondelete="SET NULL",
        ),
        nullable=True,
        index=True,
    )
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    updated_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __mapper_args__ = {"version_id_col": version, "version_id_generator": False}

    meeting: Mapped["Meeting"] = relationship(back_populates="agenda_items")
    proposer: Mapped[User | None] = relationship(foreign_keys=[proposer_user_id])
    presenter: Mapped[User | None] = relationship(foreign_keys=[presenter_user_id])
    creator: Mapped[User] = relationship(foreign_keys=[created_by])
    updater: Mapped[User] = relationship(foreign_keys=[updated_by])
    copied_from: Mapped["AgendaItem | None"] = relationship(
        remote_side=[id], foreign_keys=[copied_from_agenda_item_id]
    )

    decisions = relationship(
        "Decision", back_populates="agenda_item", foreign_keys="Decision.agenda_item_id"
    )
    actions = relationship(
        "ActionItem",
        back_populates="agenda_item",
        foreign_keys="ActionItem.agenda_item_id",
    )
    open_questions = relationship(
        "OpenQuestion",
        back_populates="agenda_item",
        foreign_keys="OpenQuestion.agenda_item_id",
    )
