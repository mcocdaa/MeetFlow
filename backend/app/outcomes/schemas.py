from datetime import date
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.domain.enums import (
    ActionPriority,
    ActionStatus,
    DecisionReviewerStatus,
    OpenQuestionStatus,
)


def _strip(value: Any) -> Any:
    return value.strip() if isinstance(value, str) else value


class StrictInput(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SourceInput(StrictInput):
    meeting_id: str | None = Field(default=None, max_length=64)
    agenda_item_id: str | None = Field(default=None, max_length=64)

    @field_validator("meeting_id", "agenda_item_id", mode="before")
    @classmethod
    def normalize_refs(cls, value: Any) -> Any:
        return _strip(value)

    @field_validator("meeting_id", "agenda_item_id")
    @classmethod
    def nonblank_refs(cls, value: str | None) -> str | None:
        if value == "":
            raise ValueError("reference must not be blank")
        return value

    @model_validator(mode="after")
    def agenda_requires_meeting(self):
        if self.agenda_item_id and not self.meeting_id:
            raise ValueError("agenda_item_id requires meeting_id")
        return self


class DecisionWrite(SourceInput):
    title: str = Field(min_length=1, max_length=300)
    decision_markdown: str = Field(min_length=1, max_length=100_000)
    rationale_markdown: str = Field(default="", max_length=100_000)
    reviewer_ids: list[str] = Field(default_factory=list, max_length=200)

    @field_validator("title", mode="before")
    @classmethod
    def normalize_title(cls, value: Any) -> Any:
        return _strip(value)

    @field_validator("title")
    @classmethod
    def nonblank_title(cls, value: str) -> str:
        if not value:
            raise ValueError("title must not be blank")
        return value

    @field_validator("decision_markdown")
    @classmethod
    def decision_nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("decision_markdown must not be blank")
        return value

    @field_validator("reviewer_ids")
    @classmethod
    def normalize_reviewers(cls, values: list[str]) -> list[str]:
        normalized = [value.strip() for value in values]
        if any(not value for value in normalized):
            raise ValueError("reviewer_ids may not contain blanks")
        return list(dict.fromkeys(normalized))


class DecisionEdit(StrictInput):
    expected_version: int = Field(ge=1)
    title: str | None = Field(default=None, min_length=1, max_length=300)
    decision_markdown: str | None = Field(
        default=None, min_length=1, max_length=100_000
    )
    rationale_markdown: str | None = Field(default=None, max_length=100_000)
    reviewer_ids: list[str] | None = Field(default=None, max_length=200)

    @field_validator("title", mode="before")
    @classmethod
    def normalize_title(cls, value: Any) -> Any:
        return _strip(value)

    @field_validator("reviewer_ids")
    @classmethod
    def normalize_reviewers(cls, values: list[str] | None) -> list[str] | None:
        if values is None:
            return None
        normalized = [value.strip() for value in values]
        if any(not value for value in normalized):
            raise ValueError("reviewer_ids may not contain blanks")
        return list(dict.fromkeys(normalized))

    @model_validator(mode="after")
    def reject_null_nonnullable(self):
        nullable = {"rationale_markdown"}
        for name in self.model_fields_set - {"expected_version"} - nullable:
            if getattr(self, name) is None:
                raise ValueError(f"{name} may not be null")
        if self.decision_markdown is not None and not self.decision_markdown.strip():
            raise ValueError("decision_markdown must not be blank")
        return self


class DecisionReviewWrite(StrictInput):
    status: DecisionReviewerStatus
    comment: str = Field(default="", max_length=2000)
    expected_version: int = Field(ge=1)

    @field_validator("status")
    @classmethod
    def response_only(cls, value: DecisionReviewerStatus) -> DecisionReviewerStatus:
        if value == DecisionReviewerStatus.pending:
            raise ValueError("review response may not be pending")
        return value


class DecisionFinalizeWrite(StrictInput):
    expected_version: int = Field(ge=1)


class DecisionSupersedeWrite(StrictInput):
    new_decision_id: str = Field(min_length=1, max_length=64)
    expected_version: int = Field(ge=1)
    expected_new_version: int = Field(ge=1)


class ActionWrite(SourceInput):
    content: str = Field(min_length=1, max_length=1000)
    owner_user_id: str | None = Field(default=None, max_length=64)
    due_date: date | None = None
    priority: ActionPriority = ActionPriority.normal

    @field_validator("content", "owner_user_id", "priority", mode="before")
    @classmethod
    def normalize(cls, value: Any) -> Any:
        return _strip(value)

    @field_validator("content")
    @classmethod
    def content_nonblank(cls, value: str) -> str:
        if not value:
            raise ValueError("content must not be blank")
        return value

    @field_validator("owner_user_id")
    @classmethod
    def owner_nonblank(cls, value: str | None) -> str | None:
        if value == "":
            raise ValueError("owner_user_id must not be blank")
        return value


class ActionEdit(StrictInput):
    expected_version: int = Field(ge=1)
    content: str | None = Field(default=None, min_length=1, max_length=1000)
    owner_user_id: str | None = Field(default=None, max_length=64)
    due_date: date | None = None
    priority: ActionPriority | None = None
    status: ActionStatus | None = None

    @field_validator("content", "owner_user_id", "priority", "status", mode="before")
    @classmethod
    def normalize(cls, value: Any) -> Any:
        return _strip(value)

    @model_validator(mode="after")
    def reject_null_nonnullable(self):
        nullable = {"owner_user_id", "due_date"}
        for name in self.model_fields_set - {"expected_version"} - nullable:
            if getattr(self, name) is None:
                raise ValueError(f"{name} may not be null")
        return self


class QuestionWrite(SourceInput):
    question_markdown: str = Field(min_length=1, max_length=100_000)
    owner_user_id: str | None = Field(default=None, max_length=64)

    @field_validator("owner_user_id", mode="before")
    @classmethod
    def normalize_owner(cls, value: Any) -> Any:
        return _strip(value)

    @field_validator("question_markdown")
    @classmethod
    def question_nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("question_markdown must not be blank")
        return value


class QuestionEdit(StrictInput):
    expected_version: int = Field(ge=1)
    question_markdown: str | None = Field(
        default=None, min_length=1, max_length=100_000
    )
    owner_user_id: str | None = Field(default=None, max_length=64)
    status: OpenQuestionStatus | None = None

    @model_validator(mode="after")
    def reject_null_nonnullable(self):
        for name in self.model_fields_set - {"expected_version", "owner_user_id"}:
            if getattr(self, name) is None:
                raise ValueError(f"{name} may not be null")
        if self.question_markdown is not None and not self.question_markdown.strip():
            raise ValueError("question_markdown must not be blank")
        return self


class QuestionScheduleWrite(StrictInput):
    meeting_id: str = Field(min_length=1, max_length=64)
    expected_version: int = Field(ge=1)
    expected_meeting_version: int = Field(ge=1)


class QuestionResolveWrite(StrictInput):
    decision_id: str | None = Field(default=None, max_length=64)
    expected_version: int = Field(ge=1)


class AgendaOutcomeMigrationWrite(StrictInput):
    target_agenda_item_id: str = Field(min_length=1, max_length=64)
    expected_source_version: int = Field(ge=1)
    expected_target_version: int = Field(ge=1)
    expected_source_meeting_version: int = Field(ge=1)
    expected_target_meeting_version: int = Field(ge=1)


class AgendaConvertWrite(StrictInput):
    expected_source_version: int = Field(ge=1)


class AgendaCopyWrite(StrictInput):
    target_meeting_id: str = Field(min_length=1, max_length=64)
    expected_source_version: int = Field(ge=1)
    expected_target_meeting_version: int = Field(ge=1)
