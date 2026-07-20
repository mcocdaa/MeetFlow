from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.domain.enums import AgendaType


def _strip(value: Any) -> Any:
    return value.strip() if isinstance(value, str) else value


class StrictInput(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AgendaWrite(StrictInput):
    title: str = Field(min_length=1, max_length=300)
    agenda_type: AgendaType
    proposer_user_id: str | None = Field(default=None, max_length=64)
    presenter_user_id: str | None = Field(default=None, max_length=64)
    estimated_minutes: int | None = Field(default=None, ge=1, le=480)
    notes_markdown: str = Field(default="", max_length=100_000)
    position: int | None = Field(default=None, ge=0)

    @field_validator(
        "title",
        "agenda_type",
        "proposer_user_id",
        "presenter_user_id",
        mode="before",
    )
    @classmethod
    def normalize(cls, value: Any) -> Any:
        return _strip(value)

    @field_validator("title")
    @classmethod
    def require_title(cls, value: str) -> str:
        if not value:
            raise ValueError("title must not be blank")
        return value

    @field_validator("proposer_user_id", "presenter_user_id")
    @classmethod
    def reject_blank_reference(cls, value: str | None) -> str | None:
        if value == "":
            raise ValueError("reference must not be blank")
        return value


class AgendaEdit(StrictInput):
    expected_version: int = Field(ge=1)
    title: str | None = Field(default=None, min_length=1, max_length=300)
    agenda_type: AgendaType | None = None
    proposer_user_id: str | None = Field(default=None, max_length=64)
    presenter_user_id: str | None = Field(default=None, max_length=64)
    estimated_minutes: int | None = Field(default=None, ge=1, le=480)
    notes_markdown: str | None = Field(default=None, max_length=100_000)

    @field_validator(
        "title",
        "agenda_type",
        "proposer_user_id",
        "presenter_user_id",
        mode="before",
    )
    @classmethod
    def normalize(cls, value: Any) -> Any:
        return _strip(value)

    @field_validator("title")
    @classmethod
    def require_title(cls, value: str | None) -> str | None:
        if value == "":
            raise ValueError("title must not be blank")
        return value

    @field_validator("proposer_user_id", "presenter_user_id")
    @classmethod
    def reject_blank_reference(cls, value: str | None) -> str | None:
        if value == "":
            raise ValueError("reference must not be blank")
        return value

    @model_validator(mode="after")
    def reject_null_nonnullable(self):
        nullable = {
            "proposer_user_id",
            "presenter_user_id",
            "estimated_minutes",
        }
        for name in self.model_fields_set - {"expected_version"} - nullable:
            if getattr(self, name) is None:
                raise ValueError(f"{name} may not be null")
        return self


class AgendaReorder(StrictInput):
    ids: list[str] = Field(min_length=1, max_length=500)
    expected_meeting_version: int = Field(ge=1)

    @field_validator("ids")
    @classmethod
    def normalize_ids(cls, values: list[str]) -> list[str]:
        normalized = [value.strip() for value in values]
        if any(not value for value in normalized):
            raise ValueError("ids may not contain blanks")
        return normalized


class AgendaCommand(StrictInput):
    expected_version: int = Field(ge=1)
