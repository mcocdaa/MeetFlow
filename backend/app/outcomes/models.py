import uuid
from datetime import date, datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import (
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    event,
    select,
)
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.auth.models import User
from app.database import Base
from app.domain.enums import (
    ActionPriority,
    ActionStatus,
    DecisionReviewerStatus,
    DecisionStatus,
    OpenQuestionStatus,
)

if TYPE_CHECKING:
    from app.agendas.models import AgendaItem
    from app.meetings.models import Meeting
    from app.projects.models import Project


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Decision(Base):
    __tablename__ = "decisions"

    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    meeting_id: Mapped[str | None] = mapped_column(
        ForeignKey("meetings.id", ondelete="SET NULL"), nullable=True, index=True
    )
    agenda_item_id: Mapped[str | None] = mapped_column(
        ForeignKey("agenda_items.id", ondelete="SET NULL"), nullable=True, index=True
    )
    title: Mapped[str] = mapped_column(String(300))
    decision_markdown: Mapped[str] = mapped_column(Text)
    rationale_markdown: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[DecisionStatus] = mapped_column(
        Enum(DecisionStatus), default=DecisionStatus.proposed, index=True
    )
    decided_by_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    supersedes_decision_id: Mapped[str | None] = mapped_column(
        ForeignKey("decisions.id", ondelete="SET NULL"), nullable=True
    )
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    __mapper_args__ = {"version_id_col": version, "version_id_generator": False}

    project: Mapped["Project"] = relationship(foreign_keys=[project_id])
    meeting: Mapped["Meeting | None"] = relationship(foreign_keys=[meeting_id])
    agenda_item: Mapped["AgendaItem | None"] = relationship(
        back_populates="decisions", foreign_keys=[agenda_item_id]
    )
    decided_by: Mapped[User | None] = relationship(foreign_keys=[decided_by_user_id])
    creator: Mapped[User] = relationship(foreign_keys=[created_by])
    supersedes: Mapped["Decision | None"] = relationship(
        remote_side=[id], foreign_keys=[supersedes_decision_id]
    )
    reviewers: Mapped[list["DecisionReviewer"]] = relationship(
        back_populates="decision",
        cascade="all, delete-orphan",
        order_by="DecisionReviewer.user_id",
    )


class DecisionReviewer(Base):
    __tablename__ = "decision_reviewers"

    decision_id: Mapped[str] = mapped_column(
        ForeignKey("decisions.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), primary_key=True)
    status: Mapped[DecisionReviewerStatus] = mapped_column(
        Enum(DecisionReviewerStatus), default=DecisionReviewerStatus.pending
    )
    responded_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    comment: Mapped[str] = mapped_column(String(2000), default="")

    decision: Mapped[Decision] = relationship(back_populates="reviewers")
    user: Mapped[User] = relationship(foreign_keys=[user_id])


class ActionItem(Base):
    __tablename__ = "action_items"

    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    meeting_id: Mapped[str | None] = mapped_column(
        ForeignKey("meetings.id", ondelete="SET NULL"), nullable=True, index=True
    )
    agenda_item_id: Mapped[str | None] = mapped_column(
        ForeignKey("agenda_items.id", ondelete="SET NULL"), nullable=True, index=True
    )
    content: Mapped[str] = mapped_column(String(1000))
    owner_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    priority: Mapped[ActionPriority] = mapped_column(
        Enum(ActionPriority), default=ActionPriority.normal
    )
    status: Mapped[ActionStatus] = mapped_column(
        Enum(ActionStatus), default=ActionStatus.open, index=True
    )
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __mapper_args__ = {"version_id_col": version, "version_id_generator": False}

    project: Mapped["Project"] = relationship(foreign_keys=[project_id])
    meeting: Mapped["Meeting | None"] = relationship(foreign_keys=[meeting_id])
    agenda_item: Mapped["AgendaItem | None"] = relationship(
        back_populates="actions", foreign_keys=[agenda_item_id]
    )
    owner_user: Mapped[User | None] = relationship(foreign_keys=[owner_user_id])
    creator: Mapped[User] = relationship(foreign_keys=[created_by])

    # Temporary compatibility for the v0.1 serializer until Task 7 replaces it.
    @hybrid_property
    def owner(self) -> str:
        return self.owner_user.display_name if self.owner_user is not None else ""


class OpenQuestion(Base):
    __tablename__ = "open_questions"

    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    meeting_id: Mapped[str | None] = mapped_column(
        ForeignKey("meetings.id", ondelete="SET NULL"), nullable=True, index=True
    )
    agenda_item_id: Mapped[str | None] = mapped_column(
        ForeignKey("agenda_items.id", ondelete="SET NULL"), nullable=True, index=True
    )
    question_markdown: Mapped[str] = mapped_column(Text)
    owner_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    status: Mapped[OpenQuestionStatus] = mapped_column(
        Enum(OpenQuestionStatus), default=OpenQuestionStatus.open, index=True
    )
    scheduled_meeting_id: Mapped[str | None] = mapped_column(
        ForeignKey("meetings.id", ondelete="SET NULL"), nullable=True
    )
    resolved_by_decision_id: Mapped[str | None] = mapped_column(
        ForeignKey("decisions.id", ondelete="SET NULL"), nullable=True
    )
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    __mapper_args__ = {"version_id_col": version, "version_id_generator": False}

    project: Mapped["Project"] = relationship(foreign_keys=[project_id])
    meeting: Mapped["Meeting | None"] = relationship(foreign_keys=[meeting_id])
    agenda_item: Mapped["AgendaItem | None"] = relationship(
        back_populates="open_questions", foreign_keys=[agenda_item_id]
    )
    owner_user: Mapped[User | None] = relationship(foreign_keys=[owner_user_id])
    scheduled_meeting: Mapped["Meeting | None"] = relationship(
        foreign_keys=[scheduled_meeting_id]
    )
    resolved_by_decision: Mapped[Decision | None] = relationship(
        foreign_keys=[resolved_by_decision_id]
    )
    creator: Mapped[User] = relationship(foreign_keys=[created_by])


@event.listens_for(ActionItem, "before_insert")
def _backfill_legacy_action_project(_mapper, connection, target: ActionItem) -> None:
    """Bridge v0.1 plugin/test inserts until the legacy action API is removed."""
    if not target.project_id and target.meeting_id:
        from app.meetings.models import Meeting

        target.project_id = connection.scalar(
            select(Meeting.project_id).where(Meeting.id == target.meeting_id)
        )
