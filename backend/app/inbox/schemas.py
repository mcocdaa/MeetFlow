from datetime import datetime
from typing import Any

from pydantic import BaseModel


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


class InboxHistoryResponse(BaseModel):
    items: list[NotificationItem]
    next_cursor: int | None
    unread_count: int


class InboxChangesResponse(BaseModel):
    notifications: list[NotificationItem]
    next_cursor: int
    has_more: bool
    unread_count: int
