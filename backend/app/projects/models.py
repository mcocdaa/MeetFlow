import uuid
from datetime import date, datetime, timezone

from sqlalchemy import Date, DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.auth.models import User
from app.database import Base
from app.domain.enums import (
    ProjectHealth,
    ProjectMemberRole,
    ProjectStatus,
    ProjectUpdateSource,
)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    name: Mapped[str] = mapped_column(String(160))
    slug: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    summary: Mapped[str] = mapped_column(String(500), default="")
    description_markdown: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[ProjectStatus] = mapped_column(
        Enum(ProjectStatus), default=ProjectStatus.planned, index=True
    )
    health: Mapped[ProjectHealth] = mapped_column(
        Enum(ProjectHealth), default=ProjectHealth.unset, index=True
    )
    lead_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )
    target_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    __mapper_args__ = {
        "version_id_col": version,
        "version_id_generator": False,
    }
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    updated_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    lead: Mapped[User | None] = relationship(foreign_keys=[lead_user_id])
    creator: Mapped[User] = relationship(foreign_keys=[created_by])
    updater: Mapped[User] = relationship(foreign_keys=[updated_by])
    memberships: Mapped[list["ProjectMember"]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
        order_by="ProjectMember.position",
    )
    updates: Mapped[list["ProjectUpdate"]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
        order_by="ProjectUpdate.created_at.desc()",
    )


class ProjectMember(Base):
    __tablename__ = "project_members"

    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id"), primary_key=True, index=True
    )
    role: Mapped[ProjectMemberRole] = mapped_column(
        Enum(ProjectMemberRole), default=ProjectMemberRole.member
    )
    position: Mapped[int] = mapped_column(Integer, default=0)

    project: Mapped[Project] = relationship(back_populates="memberships")
    user: Mapped[User] = relationship(foreign_keys=[user_id])


class ProjectUpdate(Base):
    __tablename__ = "project_updates"

    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    health: Mapped[ProjectHealth] = mapped_column(
        Enum(ProjectHealth), default=ProjectHealth.unset
    )
    content_markdown: Mapped[str] = mapped_column(Text)
    source: Mapped[ProjectUpdateSource] = mapped_column(
        Enum(ProjectUpdateSource), default=ProjectUpdateSource.human
    )
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    project: Mapped[Project] = relationship(back_populates="updates")
    creator: Mapped[User] = relationship(foreign_keys=[created_by])
