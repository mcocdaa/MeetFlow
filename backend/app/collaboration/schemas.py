from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ActivityActorRef(BaseModel):
    id: str
    username: str
    display_name: str
    avatar_color: str


class ActivitySubjectRef(BaseModel):
    type: str
    id: str


class ActivityItem(BaseModel):
    id: int
    project_id: str | None
    meeting_id: str | None
    actor: ActivityActorRef | None
    event_type: str
    subject: ActivitySubjectRef
    payload: dict[str, Any]
    created_at: datetime


class ActivityPageResponse(BaseModel):
    items: list[ActivityItem]
    next_cursor: int | None


class StrictInput(BaseModel):
    model_config = ConfigDict(extra="forbid")


def _strip(value: Any) -> Any:
    return value.strip() if isinstance(value, str) else value


class CommentWrite(StrictInput):
    target_type: str = Field(min_length=1, max_length=40)
    target_id: str = Field(min_length=1, max_length=36)
    parent_id: str | None = Field(default=None, max_length=36)
    body_markdown: str = Field(min_length=1, max_length=100_000)
    mention_user_ids: list[str] = Field(default_factory=list, max_length=200)

    @field_validator("target_type", "target_id", "parent_id", mode="before")
    @classmethod
    def normalize_refs(cls, value: Any) -> Any:
        return _strip(value)

    @field_validator("target_type", "target_id")
    @classmethod
    def require_refs(cls, value: str) -> str:
        if not value:
            raise ValueError("reference must not be blank")
        return value

    @field_validator("parent_id")
    @classmethod
    def require_parent_if_present(cls, value: str | None) -> str | None:
        if value == "":
            raise ValueError("parent_id must not be blank")
        return value

    @field_validator("body_markdown")
    @classmethod
    def normalize_body(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("body_markdown must not be blank")
        return value

    @field_validator("mention_user_ids")
    @classmethod
    def normalize_mentions(cls, values: list[str]) -> list[str]:
        values = [value.strip() for value in values]
        if any(not value for value in values):
            raise ValueError("mention_user_ids may not contain blanks")
        return values


class CommentEdit(StrictInput):
    expected_version: int = Field(ge=1)
    body_markdown: str = Field(min_length=1, max_length=100_000)
    mention_user_ids: list[str] = Field(default_factory=list, max_length=200)

    @field_validator("body_markdown")
    @classmethod
    def normalize_body(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("body_markdown must not be blank")
        return value

    @field_validator("mention_user_ids")
    @classmethod
    def normalize_mentions(cls, values: list[str]) -> list[str]:
        values = [value.strip() for value in values]
        if any(not value for value in values):
            raise ValueError("mention_user_ids may not contain blanks")
        return values


class CommentCommand(StrictInput):
    expected_version: int = Field(ge=1)
