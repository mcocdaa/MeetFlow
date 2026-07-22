from datetime import datetime
from typing import Any

from pydantic import BaseModel


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
