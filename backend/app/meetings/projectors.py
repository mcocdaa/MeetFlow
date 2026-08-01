from __future__ import annotations

from typing import Any

from app.attachments.models import Attachment
from app.auth.models import User
from app.meetings.models import MeetingAmendment, MeetingSnapshot
from app.projects.models import Project


def user_ref(user: User | None) -> dict[str, str] | None:
    if user is None:
        return None
    return {"id": user.id, "username": user.username, "display_name": user.display_name}


def project_ref(project: Project) -> dict[str, str]:
    return {"id": project.id, "name": project.name, "slug": project.slug}


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


def serialize_attachment(item: Attachment) -> dict[str, Any]:
    return {
        "id": item.id,
        "target_type": item.target_type,
        "target_id": item.target_id,
        "original_name": item.original_name,
        "mime_type": item.mime_type,
        "size": item.size,
        "attachment_type": item.attachment_type,
        "created_by": user_ref(item.creator),
        "created_at": item.created_at,
        "download_url": f"/api/attachments/{item.target_type}/{item.target_id}/{item.id}",
    }
