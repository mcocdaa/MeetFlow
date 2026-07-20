from datetime import date
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

from app.domain.enums import ProjectHealth, ProjectStatus, ProjectUpdateSource


def _strip_nonblank(value: str) -> str:
    value = value.strip()
    if not value:
        raise ValueError("value must not be blank")
    return value


def _strip_if_string(value: Any) -> Any:
    return value.strip() if isinstance(value, str) else value


class ProjectWrite(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    slug: str = Field(
        min_length=1,
        max_length=80,
        pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$",
    )
    summary: str = Field(default="", max_length=500)
    description_markdown: str = Field(default="", max_length=100_000)
    status: ProjectStatus = ProjectStatus.planned
    health: ProjectHealth = ProjectHealth.unset
    lead_user_id: str | None = None
    target_date: date | None = None
    member_ids: list[str] = Field(default_factory=list, max_length=200)

    @field_validator(
        "name",
        "slug",
        "summary",
        "status",
        "health",
        "lead_user_id",
        mode="before",
    )
    @classmethod
    def strip_ordinary_strings(cls, value: Any) -> Any:
        return _strip_if_string(value)

    @field_validator("member_ids", mode="before")
    @classmethod
    def strip_member_ids_before_validation(cls, values: Any) -> Any:
        if isinstance(values, list):
            return [_strip_if_string(value) for value in values]
        return values

    @field_validator("name", "slug")
    @classmethod
    def normalize_required_strings(cls, value: str) -> str:
        return _strip_nonblank(value)

    @field_validator("summary")
    @classmethod
    def normalize_summary(cls, value: str) -> str:
        return value.strip()

    @field_validator("lead_user_id")
    @classmethod
    def normalize_lead(cls, value: str | None) -> str | None:
        return _strip_nonblank(value) if value is not None else None

    @field_validator("member_ids")
    @classmethod
    def normalize_members(cls, values: list[str]) -> list[str]:
        return [_strip_nonblank(value) for value in values]


class ProjectEdit(BaseModel):
    expected_version: int = Field(ge=0)
    name: str | None = Field(default=None, min_length=1, max_length=160)
    slug: str | None = Field(
        default=None,
        min_length=1,
        max_length=80,
        pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$",
    )
    summary: str | None = Field(default=None, max_length=500)
    description_markdown: str | None = Field(default=None, max_length=100_000)
    status: ProjectStatus | None = None
    health: ProjectHealth | None = None
    lead_user_id: str | None = None
    target_date: date | None = None
    member_ids: list[str] | None = Field(default=None, max_length=200)

    @field_validator(
        "name",
        "slug",
        "summary",
        "status",
        "health",
        "lead_user_id",
        mode="before",
    )
    @classmethod
    def strip_ordinary_strings(cls, value: Any) -> Any:
        return _strip_if_string(value)

    @field_validator("member_ids", mode="before")
    @classmethod
    def strip_member_ids_before_validation(cls, values: Any) -> Any:
        if isinstance(values, list):
            return [_strip_if_string(value) for value in values]
        return values

    @field_validator("name", "slug")
    @classmethod
    def normalize_required_strings(cls, value: str | None) -> str | None:
        return _strip_nonblank(value) if value is not None else None

    @field_validator("summary")
    @classmethod
    def normalize_summary(cls, value: str | None) -> str | None:
        return value.strip() if value is not None else None

    @field_validator("lead_user_id")
    @classmethod
    def normalize_lead(cls, value: str | None) -> str | None:
        return _strip_nonblank(value) if value is not None else None

    @field_validator("member_ids")
    @classmethod
    def normalize_members(cls, values: list[str] | None) -> list[str] | None:
        if values is None:
            return None
        return [_strip_nonblank(value) for value in values]

    @model_validator(mode="after")
    def reject_null_for_nonnullable_properties(self):
        nullable = {"lead_user_id", "target_date"}
        for field in self.model_fields_set - {"expected_version"} - nullable:
            if getattr(self, field) is None:
                raise ValueError(f"{field} may not be null")
        return self


class ProjectUpdateWrite(BaseModel):
    health: ProjectHealth = ProjectHealth.unset
    content_markdown: str = Field(min_length=1, max_length=100_000)
    source: ProjectUpdateSource = ProjectUpdateSource.human

    @field_validator("health", "source", mode="before")
    @classmethod
    def strip_ordinary_strings(cls, value: Any) -> Any:
        return _strip_if_string(value)

    @field_validator("content_markdown")
    @classmethod
    def markdown_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("content_markdown must not be blank")
        return value
