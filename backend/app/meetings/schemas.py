from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class MeetingWrite(BaseModel):
    title: str = Field(min_length=1, max_length=240)
    project: str = Field(default="", max_length=160)
    meeting_type: str = Field(default="", max_length=120)
    meeting_date: datetime
    participants: list[str] = Field(default_factory=list, max_length=100)
    raw_notes_markdown: str = Field(default="", max_length=100_000)
    conclusions_markdown: str = Field(default="", max_length=50_000)

    @field_validator("title")
    @classmethod
    def title_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("title must not be blank")
        return value

    @field_validator("participants")
    @classmethod
    def normalize_participants(cls, values: list[str]) -> list[str]:
        return [value.strip() for value in values if value.strip()]


class ActionWrite(BaseModel):
    content: str = Field(min_length=1, max_length=500)
    owner: str = Field(default="", max_length=120)
    due_date: date | None = None
    status: Literal["open", "done"] = "open"

    @field_validator("content")
    @classmethod
    def content_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("content must not be blank")
        return value


class UpdateWrite(BaseModel):
    content_markdown: str = Field(min_length=1, max_length=20_000)

    @field_validator("content_markdown")
    @classmethod
    def update_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("content_markdown must not be blank")
        return value
