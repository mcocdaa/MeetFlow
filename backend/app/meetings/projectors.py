from __future__ import annotations

from typing import Any

from app.attachments.models import Attachment
from app.refs import project_ref, serialize_attachment as serialize_attachment_ref, user_ref
from app.auth.models import User
from app.meetings.models import MeetingAmendment, MeetingSnapshot
from app.projects.models import Project


def serialize_snapshot(item: MeetingSnapshot) -> dict[str, Any]:
    return {
        "id": item.id,
        "meeting_id": item.meeting_id,
        "completion_number": item.completion_number,
        "snapshot": item.snapshot_json,
        "created_by_user_id": item.created_by,
        "created_by": user_ref(item.creator),
        "created_at": item.created_at,
    }


def serialize_amendment(item: MeetingAmendment) -> dict[str, Any]:
    return {
        "id": item.id,
        "meeting_id": item.meeting_id,
        "reason": item.reason,
        "content_markdown": item.content_markdown,
        "created_by_user_id": item.created_by,
        "created_by": user_ref(item.creator),
        "created_at": item.created_at,
    }


def serialize_attachment(
    item: Attachment, *, can_delete: bool = False
) -> dict[str, Any]:
    result = serialize_attachment_ref(item)
    result["can_delete"] = can_delete
    return result
