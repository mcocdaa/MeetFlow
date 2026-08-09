from datetime import datetime
from typing import Any

from pydantic import BaseModel, field_serializer

from app.http import _z_iso


class NotificationActorRef(BaseModel):
    id: str
    username: str
    display_name: str
    avatar_color: str


class NotificationItem(BaseModel):
    id: int
    actor: NotificationActorRef | None
    kind: str
    subject: dict[str, str]
    project: dict[str, str] | None
    meeting: dict[str, str] | None
    source_comment: dict[str, str] | None
    data: dict[str, Any]
    read_at: datetime | None
    created_at: datetime

    @field_serializer("read_at", "created_at")
    def _z(self, value: datetime | None) -> str | None:
        return _z_iso(value) if value is not None else None


class InboxHistoryResponse(BaseModel):
    items: list[NotificationItem]
    next_cursor: int | None
    unread_count: int


class InboxChangesResponse(BaseModel):
    notifications: list[NotificationItem]
    next_cursor: int
    has_more: bool
    unread_count: int
