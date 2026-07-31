from datetime import date, datetime, time, timezone
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.domain.enums import (
    ActionPriority,
    ActionStatus,
    AgendaStatus,
    AgendaType,
    DecisionReviewerStatus,
    DecisionStatus,
    MeetingStatus,
    OpenQuestionStatus,
    ParticipationRole,
    RecurrenceFrequency,
    SeriesStatus,
)


def _strip(value: Any) -> Any:
    return value.strip() if isinstance(value, str) else value


def _required(value: str) -> str:
    value = value.strip()
    if not value:
        raise ValueError("value must not be blank")
    return value


class StrictInput(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LifecycleCommand(StrictInput):
    expected_version: int = Field(ge=1)


class AmendmentWrite(StrictInput):
    reason: str = Field(min_length=1, max_length=500)
    content_markdown: str = Field(min_length=1, max_length=100_000)
    expected_version: int = Field(ge=1)

    @field_validator("reason", mode="before")
    @classmethod
    def normalize_reason(cls, value: Any) -> Any:
        return _strip(value)

    @field_validator("reason")
    @classmethod
    def require_reason(cls, value: str) -> str:
        return _required(value)

    @field_validator("content_markdown")
    @classmethod
    def require_content(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("value must not be blank")
        return value


class StrictSnapshotModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class SnapshotParticipant(StrictSnapshotModel):
    user_id: str
    participation_role: ParticipationRole
    position: int


class SnapshotReviewer(StrictSnapshotModel):
    user_id: str
    status: DecisionReviewerStatus
    responded_at: datetime | None
    comment: str | None


class SnapshotDecision(StrictSnapshotModel):
    id: str
    project_id: str
    meeting_id: str | None
    agenda_item_id: str | None
    source_agenda_item_id: str | None
    source_tag_key: str | None
    is_derived: bool
    title: str
    decision_markdown: str
    rationale_markdown: str
    status: DecisionStatus
    decided_by_user_id: str | None
    supersedes_decision_id: str | None
    version: int
    created_by: str
    created_at: datetime
    updated_at: datetime
    reviewers: list[SnapshotReviewer]


class SnapshotAction(StrictSnapshotModel):
    id: str
    project_id: str
    meeting_id: str | None
    agenda_item_id: str | None
    source_agenda_item_id: str | None
    source_tag_key: str | None
    is_derived: bool
    content: str
    owner_user_id: str | None
    due_date: date | None
    priority: ActionPriority
    status: ActionStatus
    version: int
    created_by: str
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None


class SnapshotQuestion(StrictSnapshotModel):
    id: str
    project_id: str
    meeting_id: str | None
    agenda_item_id: str | None
    source_agenda_item_id: str | None
    source_tag_key: str | None
    is_derived: bool
    question_markdown: str
    owner_user_id: str | None
    status: OpenQuestionStatus
    scheduled_meeting_id: str | None
    resolved_by_decision_id: str | None
    converted_from_agenda_item_id: str | None
    version: int
    created_by: str
    created_at: datetime
    updated_at: datetime


class SnapshotAgendaItem(StrictSnapshotModel):
    id: str
    meeting_id: str
    title: str
    agenda_type: AgendaType
    proposer_user_id: str | None
    presenter_user_id: str | None
    estimated_minutes: int | None
    actual_duration_seconds: int | None
    notes_markdown: str
    status: AgendaStatus
    position: int
    carry_from_open_question_id: str | None
    copied_from_agenda_item_id: str | None
    version: int
    created_by: str
    updated_by: str
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    decisions: list[SnapshotDecision]
    actions: list[SnapshotAction]
    open_questions: list[SnapshotQuestion]


class SnapshotAmendment(StrictSnapshotModel):
    id: str
    reason: str
    content_markdown: str
    created_by: str
    created_at: datetime


class SnapshotMeeting(StrictSnapshotModel):
    id: str
    project_id: str
    series_id: str | None
    title: str
    purpose_markdown: str
    scheduled_start: datetime
    scheduled_end: datetime
    status_before_completion: MeetingStatus
    host_user_id: str | None
    recorder_user_id: str | None
    summary_markdown: str
    raw_notes_markdown: str
    version_before_completion: int
    created_by: str
    updated_by: str
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    participants: list[SnapshotParticipant]


class MeetingSnapshotDocument(StrictSnapshotModel):
    schema_version: int = 1
    meeting: SnapshotMeeting
    agenda_items: list[SnapshotAgendaItem]
    meeting_decisions: list[SnapshotDecision]
    meeting_actions: list[SnapshotAction]
    meeting_open_questions: list[SnapshotQuestion]
    amendments: list[SnapshotAmendment]


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("datetime must include a timezone offset")
    return value.astimezone(timezone.utc)


class ParticipantWrite(StrictInput):
    user_id: str = Field(min_length=1, max_length=64)
    participation_role: ParticipationRole = ParticipationRole.attendee

    @field_validator("user_id", "participation_role", mode="before")
    @classmethod
    def normalize(cls, value: Any) -> Any:
        return _strip(value)

    @field_validator("user_id")
    @classmethod
    def require_user(cls, value: str) -> str:
        return _required(value)


class StandingAgendaWrite(StrictInput):
    title: str = Field(min_length=1, max_length=240)
    agenda_type: AgendaType = AgendaType.discussion
    default_owner_user_id: str | None = Field(default=None, max_length=64)
    default_duration_minutes: int | None = Field(default=None, ge=1, le=1440)

    @field_validator("title", "agenda_type", "default_owner_user_id", mode="before")
    @classmethod
    def normalize(cls, value: Any) -> Any:
        return _strip(value)

    @field_validator("title")
    @classmethod
    def require_title(cls, value: str) -> str:
        return _required(value)

    @field_validator("default_owner_user_id")
    @classmethod
    def require_owner_if_present(cls, value: str | None) -> str | None:
        return _required(value) if value is not None else None


class MeetingSeriesWrite(StrictInput):
    title: str = Field(min_length=1, max_length=240)
    purpose_markdown: str = Field(default="", max_length=100_000)
    recurrence_description: str = Field(default="", max_length=500)
    recurrence_frequency: RecurrenceFrequency | None = None
    recurrence_interval: int = Field(default=1, ge=1, le=365)
    recurrence_weekday: int | None = Field(default=None, ge=0, le=6)
    recurrence_month_day: int | None = Field(default=None, ge=1, le=31)
    recurrence_month: int | None = Field(default=None, ge=1, le=12)
    recurrence_local_time: time | None = None
    recurrence_timezone: str | None = Field(default=None, max_length=64)
    recurrence_anchor_date: date | None = None
    default_duration_minutes: int = Field(default=60, ge=1, le=1440)
    default_host_user_id: str | None = Field(default=None, max_length=64)
    default_recorder_user_id: str | None = Field(default=None, max_length=64)
    status: SeriesStatus = SeriesStatus.active
    participants: list[ParticipantWrite] = Field(default_factory=list, max_length=200)
    standing_items: list[StandingAgendaWrite] = Field(
        default_factory=list, max_length=200
    )

    @field_validator(
        "title",
        "recurrence_description",
        "recurrence_timezone",
        "default_host_user_id",
        "default_recorder_user_id",
        "status",
        mode="before",
    )
    @classmethod
    def normalize(cls, value: Any) -> Any:
        return _strip(value)

    @field_validator("title")
    @classmethod
    def require_title(cls, value: str) -> str:
        return _required(value)

    @field_validator("recurrence_description")
    @classmethod
    def normalize_recurrence(cls, value: str) -> str:
        return value.strip()

    @field_validator("default_host_user_id", "default_recorder_user_id")
    @classmethod
    def require_user_if_present(cls, value: str | None) -> str | None:
        return _required(value) if value is not None else None

    @model_validator(mode="after")
    def validate_recurrence(self):
        if self.recurrence_frequency is None:
            return self
        if (
            self.recurrence_local_time is None
            or self.recurrence_timezone is None
            or self.recurrence_anchor_date is None
        ):
            raise ValueError("recurrence requires local time, timezone, and anchor date")
        try:
            ZoneInfo(self.recurrence_timezone)
        except (ValueError, ZoneInfoNotFoundError) as exc:
            raise ValueError("recurrence timezone must be an IANA timezone") from exc
        if self.recurrence_frequency == RecurrenceFrequency.weekly and self.recurrence_weekday is None:
            raise ValueError("weekly recurrence requires recurrence_weekday")
        if self.recurrence_frequency == RecurrenceFrequency.monthly and self.recurrence_month_day is None:
            raise ValueError("monthly recurrence requires recurrence_month_day")
        if self.recurrence_frequency == RecurrenceFrequency.yearly and (
            self.recurrence_month is None or self.recurrence_month_day is None
        ):
            raise ValueError("yearly recurrence requires recurrence_month and recurrence_month_day")
        return self


class MeetingSeriesEdit(StrictInput):
    expected_version: int = Field(ge=0)
    title: str | None = Field(default=None, min_length=1, max_length=240)
    purpose_markdown: str | None = Field(default=None, max_length=100_000)
    recurrence_description: str | None = Field(default=None, max_length=500)
    recurrence_frequency: RecurrenceFrequency | None = None
    recurrence_interval: int | None = Field(default=None, ge=1, le=365)
    recurrence_weekday: int | None = Field(default=None, ge=0, le=6)
    recurrence_month_day: int | None = Field(default=None, ge=1, le=31)
    recurrence_month: int | None = Field(default=None, ge=1, le=12)
    recurrence_local_time: time | None = None
    recurrence_timezone: str | None = Field(default=None, max_length=64)
    recurrence_anchor_date: date | None = None
    default_duration_minutes: int | None = Field(default=None, ge=1, le=1440)
    default_host_user_id: str | None = Field(default=None, max_length=64)
    default_recorder_user_id: str | None = Field(default=None, max_length=64)
    status: SeriesStatus | None = None
    participants: list[ParticipantWrite] | None = Field(default=None, max_length=200)
    standing_items: list[StandingAgendaWrite] | None = Field(
        default=None, max_length=200
    )

    @field_validator(
        "title",
        "recurrence_description",
        "recurrence_timezone",
        "default_host_user_id",
        "default_recorder_user_id",
        "status",
        mode="before",
    )
    @classmethod
    def normalize(cls, value: Any) -> Any:
        return _strip(value)

    @field_validator("title")
    @classmethod
    def require_title(cls, value: str | None) -> str | None:
        return _required(value) if value is not None else None

    @field_validator("recurrence_description")
    @classmethod
    def normalize_recurrence(cls, value: str | None) -> str | None:
        return value.strip() if value is not None else None

    @field_validator("default_host_user_id", "default_recorder_user_id")
    @classmethod
    def require_user_if_present(cls, value: str | None) -> str | None:
        return _required(value) if value is not None else None

    @model_validator(mode="after")
    def reject_null_nonnullable(self):
        nullable = {
            "default_host_user_id",
            "default_recorder_user_id",
            "recurrence_frequency",
            "recurrence_weekday",
            "recurrence_month_day",
            "recurrence_month",
            "recurrence_local_time",
            "recurrence_timezone",
            "recurrence_anchor_date",
        }
        for name in self.model_fields_set - {"expected_version"} - nullable:
            if getattr(self, name) is None:
                raise ValueError(f"{name} may not be null")
        return self

    @model_validator(mode="after")
    def validate_explicit_recurrence(self):
        if self.recurrence_frequency is None:
            return self
        if (
            self.recurrence_local_time is None
            or self.recurrence_timezone is None
            or self.recurrence_anchor_date is None
        ):
            raise ValueError("recurrence requires local time, timezone, and anchor date")
        try:
            ZoneInfo(self.recurrence_timezone)
        except (ValueError, ZoneInfoNotFoundError) as exc:
            raise ValueError("recurrence timezone must be an IANA timezone") from exc
        if self.recurrence_frequency == RecurrenceFrequency.weekly and self.recurrence_weekday is None:
            raise ValueError("weekly recurrence requires recurrence_weekday")
        if self.recurrence_frequency == RecurrenceFrequency.monthly and self.recurrence_month_day is None:
            raise ValueError("monthly recurrence requires recurrence_month_day")
        if self.recurrence_frequency == RecurrenceFrequency.yearly and (
            self.recurrence_month is None or self.recurrence_month_day is None
        ):
            raise ValueError("yearly recurrence requires recurrence_month and recurrence_month_day")
        return self


class _TimeWindow(StrictInput):
    scheduled_start: datetime
    scheduled_end: datetime

    @field_validator("scheduled_start", "scheduled_end")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        return _aware(value)

    @model_validator(mode="after")
    def end_after_start(self):
        if self.scheduled_end <= self.scheduled_start:
            raise ValueError("scheduled_end must be after scheduled_start")
        return self


class OccurrenceWrite(_TimeWindow):
    title: str = Field(min_length=1, max_length=240)

    @field_validator("title", mode="before")
    @classmethod
    def normalize_title(cls, value: Any) -> Any:
        return _strip(value)

    @field_validator("title")
    @classmethod
    def require_title(cls, value: str) -> str:
        return _required(value)


class MeetingWrite(_TimeWindow):
    title: str = Field(min_length=1, max_length=240)
    purpose_markdown: str = Field(default="", max_length=100_000)
    host_user_id: str | None = Field(default=None, max_length=64)
    recorder_user_id: str | None = Field(default=None, max_length=64)
    summary_markdown: str = Field(default="", max_length=100_000)
    raw_notes_markdown: str = Field(default="", max_length=200_000)
    participants: list[ParticipantWrite] = Field(default_factory=list, max_length=200)

    @field_validator("title", "host_user_id", "recorder_user_id", mode="before")
    @classmethod
    def normalize(cls, value: Any) -> Any:
        return _strip(value)

    @field_validator("title")
    @classmethod
    def require_title(cls, value: str) -> str:
        return _required(value)

    @field_validator("host_user_id", "recorder_user_id")
    @classmethod
    def require_user_if_present(cls, value: str | None) -> str | None:
        return _required(value) if value is not None else None


class MeetingEdit(StrictInput):
    expected_version: int = Field(ge=0)
    title: str | None = Field(default=None, min_length=1, max_length=240)
    purpose_markdown: str | None = Field(default=None, max_length=100_000)
    scheduled_start: datetime | None = None
    scheduled_end: datetime | None = None
    host_user_id: str | None = Field(default=None, max_length=64)
    recorder_user_id: str | None = Field(default=None, max_length=64)
    summary_markdown: str | None = Field(default=None, max_length=100_000)
    raw_notes_markdown: str | None = Field(default=None, max_length=200_000)
    participants: list[ParticipantWrite] | None = Field(default=None, max_length=200)

    @field_validator("title", "host_user_id", "recorder_user_id", mode="before")
    @classmethod
    def normalize(cls, value: Any) -> Any:
        return _strip(value)

    @field_validator("title")
    @classmethod
    def require_title(cls, value: str | None) -> str | None:
        return _required(value) if value is not None else None

    @field_validator("host_user_id", "recorder_user_id")
    @classmethod
    def require_user_if_present(cls, value: str | None) -> str | None:
        return _required(value) if value is not None else None

    @field_validator("scheduled_start", "scheduled_end")
    @classmethod
    def require_timezone(cls, value: datetime | None) -> datetime | None:
        return _aware(value) if value is not None else None

    @model_validator(mode="after")
    def reject_invalid_values(self):
        nullable = {"host_user_id", "recorder_user_id"}
        for name in self.model_fields_set - {"expected_version"} - nullable:
            if getattr(self, name) is None:
                raise ValueError(f"{name} may not be null")
        if (
            self.scheduled_start is not None
            and self.scheduled_end is not None
            and self.scheduled_end <= self.scheduled_start
        ):
            raise ValueError("scheduled_end must be after scheduled_start")
        return self


# Compatibility aliases used only by transitional routers/tests.
SeriesParticipantWrite = ParticipantWrite
StandingAgendaItemWrite = StandingAgendaWrite
