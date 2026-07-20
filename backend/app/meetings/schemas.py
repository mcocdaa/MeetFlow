from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

from app.domain.enums import AgendaType, MeetingStatus, ParticipationRole, SeriesStatus


def _strip(value: Any) -> Any:
    return value.strip() if isinstance(value, str) else value


def _required(value: str) -> str:
    value = value.strip()
    if not value:
        raise ValueError("value must not be blank")
    return value


class ParticipantWrite(BaseModel):
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


class StandingAgendaWrite(BaseModel):
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


class MeetingSeriesWrite(BaseModel):
    title: str = Field(min_length=1, max_length=240)
    purpose_markdown: str = Field(default="", max_length=100_000)
    recurrence_description: str = Field(default="", max_length=500)
    default_duration_minutes: int = Field(default=60, ge=1, le=1440)
    default_host_user_id: str | None = Field(default=None, max_length=64)
    default_recorder_user_id: str | None = Field(default=None, max_length=64)
    status: SeriesStatus = SeriesStatus.active
    participants: list[ParticipantWrite] = Field(default_factory=list, max_length=200)
    standing_items: list[StandingAgendaWrite] = Field(default_factory=list, max_length=200)

    @field_validator(
        "title",
        "recurrence_description",
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


class MeetingSeriesEdit(BaseModel):
    expected_version: int = Field(ge=0)
    title: str | None = Field(default=None, min_length=1, max_length=240)
    purpose_markdown: str | None = Field(default=None, max_length=100_000)
    recurrence_description: str | None = Field(default=None, max_length=500)
    default_duration_minutes: int | None = Field(default=None, ge=1, le=1440)
    default_host_user_id: str | None = Field(default=None, max_length=64)
    default_recorder_user_id: str | None = Field(default=None, max_length=64)
    status: SeriesStatus | None = None
    participants: list[ParticipantWrite] | None = Field(default=None, max_length=200)
    standing_items: list[StandingAgendaWrite] | None = Field(default=None, max_length=200)

    @field_validator(
        "title",
        "recurrence_description",
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
        nullable = {"default_host_user_id", "default_recorder_user_id"}
        for name in self.model_fields_set - {"expected_version"} - nullable:
            if getattr(self, name) is None:
                raise ValueError(f"{name} may not be null")
        return self


class _TimeWindow(BaseModel):
    scheduled_start: datetime
    scheduled_end: datetime

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
    status: MeetingStatus = MeetingStatus.draft
    host_user_id: str | None = Field(default=None, max_length=64)
    recorder_user_id: str | None = Field(default=None, max_length=64)
    summary_markdown: str = Field(default="", max_length=100_000)
    raw_notes_markdown: str = Field(default="", max_length=200_000)
    participants: list[ParticipantWrite] = Field(default_factory=list, max_length=200)

    @field_validator("title", "status", "host_user_id", "recorder_user_id", mode="before")
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


class MeetingEdit(BaseModel):
    expected_version: int = Field(ge=0)
    title: str | None = Field(default=None, min_length=1, max_length=240)
    purpose_markdown: str | None = Field(default=None, max_length=100_000)
    scheduled_start: datetime | None = None
    scheduled_end: datetime | None = None
    status: MeetingStatus | None = None
    host_user_id: str | None = Field(default=None, max_length=64)
    recorder_user_id: str | None = Field(default=None, max_length=64)
    summary_markdown: str | None = Field(default=None, max_length=100_000)
    raw_notes_markdown: str | None = Field(default=None, max_length=200_000)
    participants: list[ParticipantWrite] | None = Field(default=None, max_length=200)

    @field_validator("title", "status", "host_user_id", "recorder_user_id", mode="before")
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
