import uuid
from datetime import date, datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import (
    JSON,
    Date,
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
from app.domain.enums import AgendaType, MeetingStatus, ParticipationRole, SeriesStatus
from app.projects.models import Project

if TYPE_CHECKING:
    from app.agendas.models import AgendaItem


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class MeetingSeries(Base):
    __tablename__ = "meeting_series"

    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(240))
    purpose_markdown: Mapped[str] = mapped_column(Text, default="")
    recurrence_description: Mapped[str] = mapped_column(String(500), default="")
    default_duration_minutes: Mapped[int] = mapped_column(Integer, default=60)
    default_host_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    default_recorder_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    status: Mapped[SeriesStatus] = mapped_column(
        Enum(SeriesStatus), default=SeriesStatus.active, index=True
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

    __mapper_args__ = {"version_id_col": version, "version_id_generator": False}

    project: Mapped[Project] = relationship(foreign_keys=[project_id])
    default_host: Mapped[User | None] = relationship(
        foreign_keys=[default_host_user_id]
    )
    default_recorder: Mapped[User | None] = relationship(
        foreign_keys=[default_recorder_user_id]
    )
    creator: Mapped[User] = relationship(foreign_keys=[created_by])
    updater: Mapped[User] = relationship(foreign_keys=[updated_by])
    participants: Mapped[list["SeriesParticipant"]] = relationship(
        back_populates="series",
        cascade="all, delete-orphan",
        order_by="SeriesParticipant.position",
    )
    standing_items: Mapped[list["StandingAgendaItem"]] = relationship(
        back_populates="series",
        cascade="all, delete-orphan",
        order_by="StandingAgendaItem.position",
    )


class SeriesParticipant(Base):
    __tablename__ = "series_participants"

    series_id: Mapped[str] = mapped_column(
        ForeignKey("meeting_series.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), primary_key=True)
    participation_role: Mapped[ParticipationRole] = mapped_column(
        Enum(ParticipationRole), default=ParticipationRole.attendee
    )
    position: Mapped[int] = mapped_column(Integer, default=0)

    series: Mapped[MeetingSeries] = relationship(back_populates="participants")
    user: Mapped[User] = relationship(foreign_keys=[user_id])


class StandingAgendaItem(Base):
    __tablename__ = "standing_agenda_items"

    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    series_id: Mapped[str] = mapped_column(
        ForeignKey("meeting_series.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(240))
    agenda_type: Mapped[AgendaType] = mapped_column(
        Enum(AgendaType), default=AgendaType.discussion
    )
    default_owner_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    default_duration_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    position: Mapped[int] = mapped_column(Integer, default=0)

    series: Mapped[MeetingSeries] = relationship(back_populates="standing_items")
    default_owner: Mapped[User | None] = relationship(
        foreign_keys=[default_owner_user_id]
    )


class Meeting(Base):
    __tablename__ = "meetings"

    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    series_id: Mapped[str | None] = mapped_column(
        ForeignKey("meeting_series.id", ondelete="SET NULL"), nullable=True, index=True
    )
    title: Mapped[str] = mapped_column(String(240), index=True)
    purpose_markdown: Mapped[str] = mapped_column(Text, default="")
    scheduled_start: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), index=True
    )
    scheduled_end: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[MeetingStatus] = mapped_column(
        Enum(MeetingStatus), default=MeetingStatus.draft, index=True
    )
    host_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    recorder_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    summary_markdown: Mapped[str] = mapped_column(Text, default="")
    raw_notes_markdown: Mapped[str] = mapped_column(Text, default="")
    current_snapshot_id: Mapped[str | None] = mapped_column(
        ForeignKey(
            "meeting_snapshots.id", use_alter=True, name="fk_meeting_current_snapshot"
        ),
        nullable=True,
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

    project: Mapped[Project] = relationship(foreign_keys=[project_id])
    series: Mapped[MeetingSeries | None] = relationship(foreign_keys=[series_id])
    host: Mapped[User | None] = relationship(foreign_keys=[host_user_id])
    recorder: Mapped[User | None] = relationship(foreign_keys=[recorder_user_id])
    creator: Mapped[User] = relationship(foreign_keys=[created_by])
    updater: Mapped[User] = relationship(foreign_keys=[updated_by])
    participants: Mapped[list["MeetingParticipant"]] = relationship(
        back_populates="meeting",
        cascade="all, delete-orphan",
        order_by="MeetingParticipant.position",
    )
    snapshots: Mapped[list["MeetingSnapshot"]] = relationship(
        back_populates="meeting",
        cascade="all, delete-orphan",
        foreign_keys="MeetingSnapshot.meeting_id",
    )
    current_snapshot: Mapped["MeetingSnapshot | None"] = relationship(
        foreign_keys=[current_snapshot_id], post_update=True
    )
    amendments: Mapped[list["MeetingAmendment"]] = relationship(
        back_populates="meeting",
        cascade="all, delete-orphan",
        order_by="MeetingAmendment.created_at",
    )
    agenda_items: Mapped[list["AgendaItem"]] = relationship(
        back_populates="meeting",
        cascade="all, delete-orphan",
        order_by="(AgendaItem.position, AgendaItem.id)",
    )


class MeetingParticipant(Base):
    __tablename__ = "meeting_participants"

    meeting_id: Mapped[str] = mapped_column(
        ForeignKey("meetings.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), primary_key=True)
    participation_role: Mapped[ParticipationRole] = mapped_column(
        Enum(ParticipationRole), default=ParticipationRole.attendee
    )
    position: Mapped[int] = mapped_column(Integer, default=0)

    meeting: Mapped[Meeting] = relationship(back_populates="participants")
    user: Mapped[User] = relationship(foreign_keys=[user_id])


class MeetingSnapshot(Base):
    __tablename__ = "meeting_snapshots"
    __table_args__ = (UniqueConstraint("meeting_id", "completion_number"),)

    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    meeting_id: Mapped[str] = mapped_column(
        ForeignKey("meetings.id", ondelete="CASCADE"), index=True
    )
    completion_number: Mapped[int] = mapped_column(Integer)
    snapshot_json: Mapped[dict] = mapped_column(JSON)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )

    meeting: Mapped[Meeting] = relationship(
        back_populates="snapshots", foreign_keys=[meeting_id]
    )
    creator: Mapped[User] = relationship(foreign_keys=[created_by])


class MeetingAmendment(Base):
    __tablename__ = "meeting_amendments"

    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    meeting_id: Mapped[str] = mapped_column(
        ForeignKey("meetings.id", ondelete="CASCADE"), index=True
    )
    reason: Mapped[str] = mapped_column(String(500))
    content_markdown: Mapped[str] = mapped_column(Text)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )

    meeting: Mapped[Meeting] = relationship(back_populates="amendments")
    creator: Mapped[User] = relationship(foreign_keys=[created_by])


# Transitional v0.1 tables remain mapped until their APIs are replaced in Task 7.
class ActionItem(Base):
    __tablename__ = "action_items"
    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    meeting_id: Mapped[str] = mapped_column(
        ForeignKey("meetings.id", ondelete="CASCADE"), index=True
    )
    content: Mapped[str] = mapped_column(String(500))
    owner: Mapped[str] = mapped_column(String(120), default="")
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="open", index=True)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class MeetingUpdate(Base):
    __tablename__ = "meeting_updates"
    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    meeting_id: Mapped[str] = mapped_column(
        ForeignKey("meetings.id", ondelete="CASCADE"), index=True
    )
    content_markdown: Mapped[str] = mapped_column(Text)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )


class Attachment(Base):
    __tablename__ = "attachments"
    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    meeting_id: Mapped[str] = mapped_column(
        ForeignKey("meetings.id", ondelete="CASCADE"), index=True
    )
    original_name: Mapped[str] = mapped_column(String(255))
    stored_name: Mapped[str] = mapped_column(String(255), unique=True)
    mime_type: Mapped[str] = mapped_column(String(160))
    size: Mapped[int] = mapped_column(Integer)
    attachment_type: Mapped[str] = mapped_column(String(20))
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
