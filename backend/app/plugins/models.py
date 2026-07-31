import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, JSON, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.meetings.models import utcnow


class PluginState(Base):
    __tablename__ = "plugin_states"

    plugin_id: Mapped[str] = mapped_column(String(120), primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_by: Mapped[str | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class PluginConfig(Base):
    __tablename__ = "plugin_configs"

    plugin_id: Mapped[str] = mapped_column(String(120), primary_key=True)
    config_key: Mapped[str] = mapped_column(String(120), primary_key=True)
    stored_value: Mapped[str] = mapped_column(Text)
    is_secret: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class PluginJobStatus(StrEnum):
    queued = "queued"
    requesting = "requesting"
    succeeded = "succeeded"
    failed = "failed"
    interrupted = "interrupted"
    canceled = "canceled"


class PluginEventStatus(StrEnum):
    queued = "queued"
    processing = "processing"
    succeeded = "succeeded"
    failed = "failed"


class PluginEvent(Base):
    __tablename__ = "plugin_events"
    __table_args__ = (
        Index("ix_plugin_events_claim", "status", "next_attempt_at"),
    )

    event_id: Mapped[str] = mapped_column(String(256), primary_key=True)
    event_type: Mapped[str] = mapped_column(String(120), index=True)
    payload_version: Mapped[int] = mapped_column(Integer, default=1)
    target_type: Mapped[str] = mapped_column(String(40), index=True)
    target_id: Mapped[str] = mapped_column(String(36), index=True)
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    status: Mapped[PluginEventStatus] = mapped_column(
        String(20), default=PluginEventStatus.queued, index=True
    )
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    next_attempt_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    claimed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )


class PluginJob(Base):
    __tablename__ = "plugin_jobs"
    __table_args__ = (
        Index(
            "ix_plugin_jobs_dedupe",
            "dedupe_key",
            "status",
            unique=True,
            sqlite_where=text("status IN ('queued', 'requesting')"),
        ),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    plugin_id: Mapped[str] = mapped_column(String(120), index=True)
    action_id: Mapped[str] = mapped_column(String(160), index=True)
    target_type: Mapped[str] = mapped_column(String(40), index=True)
    target_id: Mapped[str] = mapped_column(String(36), index=True)
    dedupe_key: Mapped[str] = mapped_column(String(256))
    status: Mapped[PluginJobStatus] = mapped_column(
        String(20), default=PluginJobStatus.queued, index=True
    )
    input_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    context_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    result_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    rerun_of_id: Mapped[str | None] = mapped_column(
        ForeignKey("plugin_jobs.id"), nullable=True, index=True
    )
    applied_by: Mapped[str | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    applied_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    dismissed_by: Mapped[str | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    dismissed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
