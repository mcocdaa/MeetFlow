import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.auth.models import User
from app.database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ActivityEvent(Base):
    __tablename__ = "activity_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[str | None] = mapped_column(
        ForeignKey("projects.id", ondelete="SET NULL"), nullable=True, index=True
    )
    meeting_id: Mapped[str | None] = mapped_column(
        ForeignKey("meetings.id", ondelete="SET NULL"), nullable=True, index=True
    )
    actor_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    event_type: Mapped[str] = mapped_column(String(80), index=True)
    subject_type: Mapped[str] = mapped_column(String(40))
    subject_id: Mapped[str] = mapped_column(String(36), index=True)
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )

    actor: Mapped[User | None] = relationship(foreign_keys=[actor_user_id])


class Comment(Base):
    __tablename__ = "comments"
    __table_args__ = (Index("ix_comments_target", "target_type", "target_id"),)

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    meeting_id: Mapped[str | None] = mapped_column(
        ForeignKey("meetings.id", ondelete="SET NULL"), nullable=True, index=True
    )
    target_type: Mapped[str] = mapped_column(String(40))
    target_id: Mapped[str] = mapped_column(String(36))
    parent_id: Mapped[str | None] = mapped_column(
        ForeignKey("comments.id", ondelete="CASCADE"), nullable=True, index=True
    )
    body_markdown: Mapped[str | None] = mapped_column(Text, nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    edited_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    __mapper_args__ = {"version_id_col": version, "version_id_generator": False}

    creator: Mapped[User] = relationship(foreign_keys=[created_by])
    parent: Mapped["Comment | None"] = relationship(
        remote_side=[id], back_populates="replies", foreign_keys=[parent_id]
    )
    replies: Mapped[list["Comment"]] = relationship(
        back_populates="parent",
        foreign_keys=[parent_id],
        order_by="(Comment.created_at, Comment.id)",
    )
    mentions: Mapped[list["CommentMention"]] = relationship(
        back_populates="comment",
        cascade="all, delete-orphan",
        order_by="CommentMention.user_id",
    )


class CommentMention(Base):
    __tablename__ = "comment_mentions"

    comment_id: Mapped[str] = mapped_column(
        ForeignKey("comments.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )

    comment: Mapped[Comment] = relationship(back_populates="mentions")
    user: Mapped[User] = relationship(foreign_keys=[user_id])
