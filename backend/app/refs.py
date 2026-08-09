from typing import Any

from app.attachments.models import Attachment
from app.auth.models import User
from app.projects.models import Project


def user_ref(user: User | None) -> dict[str, str] | None:
    if user is None:
        return None
    return {
        "id": user.id,
        "username": user.username,
        "display_name": user.display_name,
        "avatar_color": user.avatar_color,
    }


def project_ref(project: Project) -> dict[str, str]:
    return {"id": project.id, "name": project.name, "slug": project.slug}


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
        "download_url": (
            f"/api/attachments/{item.target_type}/{item.target_id}/{item.id}"
        ),
        "preview_url": (
            f"/api/attachments/{item.target_type}/{item.target_id}/{item.id}/preview"
        ),
    }
