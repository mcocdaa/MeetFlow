from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, Request, UploadFile
from fastapi.responses import FileResponse, PlainTextResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.agendas.models import AgendaItem
from app.attachments.models import Attachment
from app.attachments.storage import sniff_inline_image
from app.auth.dependencies import current_user
from app.auth.models import User, UserRole
from app.database import get_session
from app.errors import AppError
from app.meetings.models import Meeting
from app.projects.models import Project

TEXT_SUFFIXES = {".md", ".txt", ".json", ".yaml", ".yml", ".py", ".log"}
TEXT_PREVIEW_MAX_BYTES = 512 * 1024

router = APIRouter(prefix="/api/attachments", tags=["attachments"])


def require_target(session: Session, target_type: str, target_id: str):
    model = {"project": Project, "meeting": Meeting, "agenda_item": AgendaItem}.get(
        target_type
    )
    if model is None or session.get(model, target_id) is None:
        raise AppError(404, "attachment_target_not_found", "附件目标不存在")


def require_attachment(
    session: Session, target_type: str, target_id: str, attachment_id: str
) -> Attachment:
    attachment = session.scalar(
        select(Attachment)
        .where(
            Attachment.id == attachment_id,
            Attachment.target_type == target_type,
            Attachment.target_id == target_id,
        )
        .options(joinedload(Attachment.creator))
    )
    if attachment is None:
        raise AppError(404, "attachment_not_found", "附件不存在")
    return attachment


def serialize(item: Attachment) -> dict[str, Any]:
    return {
        "id": item.id,
        "target_type": item.target_type,
        "target_id": item.target_id,
        "original_name": item.original_name,
        "mime_type": item.mime_type,
        "size": item.size,
        "attachment_type": item.attachment_type,
        "created_by": {
            "id": item.creator.id,
            "username": item.creator.username,
            "display_name": item.creator.display_name,
        },
        "created_at": item.created_at,
        "download_url": (
            f"/api/attachments/{item.target_type}/{item.target_id}/{item.id}"
        ),
        "preview_url": (
            f"/api/attachments/{item.target_type}/{item.target_id}/{item.id}/preview"
        ),
    }


@router.get("/{target_type}/{target_id}")
def list_attachments(
    target_type: str,
    target_id: str,
    _user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> list[dict[str, Any]]:
    require_target(session, target_type, target_id)
    rows = session.scalars(
        select(Attachment)
        .where(Attachment.target_type == target_type, Attachment.target_id == target_id)
        .options(joinedload(Attachment.creator))
        .order_by(Attachment.created_at.desc(), Attachment.id.desc())
    )
    return [serialize(row) for row in rows]


@router.post("/{target_type}/{target_id}", status_code=201)
async def upload_attachment(
    target_type: str,
    target_id: str,
    request: Request,
    file: UploadFile = File(...),
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    require_target(session, target_type, target_id)
    storage = request.app.state.attachment_storage
    stored_name, final_path, size = await storage.save(target_type, target_id, file)
    detected_image = sniff_inline_image(final_path)
    attachment = Attachment(
        target_type=target_type,
        target_id=target_id,
        original_name=Path(file.filename or "file").name[:255],
        stored_name=stored_name,
        mime_type=detected_image or "application/octet-stream",
        size=size,
        attachment_type="image" if detected_image else "file",
        created_by=user.id,
    )
    session.add(attachment)
    try:
        session.commit()
    except Exception:
        session.rollback()
        final_path.unlink(missing_ok=True)
        raise
    session.refresh(attachment)
    _ = attachment.creator
    return serialize(attachment)


def attachment_file(request: Request, item: Attachment) -> Path:
    path = request.app.state.attachment_storage.attachment_path(
        item.target_type, item.target_id, item.stored_name
    )
    if not path.is_file():
        raise AppError(404, "attachment_file_missing", "附件文件不存在")
    return path


@router.get("/{target_type}/{target_id}/{attachment_id}")
def download_attachment(
    target_type: str,
    target_id: str,
    attachment_id: str,
    request: Request,
    _user: User = Depends(current_user),
    session: Session = Depends(get_session),
):
    item = require_attachment(session, target_type, target_id, attachment_id)
    path = attachment_file(request, item)
    disposition = "inline" if item.attachment_type == "image" else "attachment"
    return FileResponse(
        path,
        media_type=item.mime_type,
        filename=item.original_name,
        content_disposition_type=disposition,
        headers={"X-Content-Type-Options": "nosniff"},
    )


@router.get("/{target_type}/{target_id}/{attachment_id}/preview")
def preview_attachment(
    target_type: str,
    target_id: str,
    attachment_id: str,
    request: Request,
    _user: User = Depends(current_user),
    session: Session = Depends(get_session),
):
    item = require_attachment(session, target_type, target_id, attachment_id)
    path = attachment_file(request, item)
    if path.suffix.lower() not in TEXT_SUFFIXES or item.size > TEXT_PREVIEW_MAX_BYTES:
        raise AppError(415, "attachment_preview_unsupported", "该附件不支持文本预览")
    return PlainTextResponse(
        path.read_text(encoding="utf-8", errors="replace"),
        headers={"X-Content-Type-Options": "nosniff"},
    )


@router.delete("/{target_type}/{target_id}/{attachment_id}", status_code=204)
def delete_attachment(
    target_type: str,
    target_id: str,
    attachment_id: str,
    request: Request,
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> None:
    item = require_attachment(session, target_type, target_id, attachment_id)
    if item.created_by != user.id and user.role != UserRole.ADMIN:
        raise AppError(403, "attachment_delete_forbidden", "只能删除自己上传的附件")
    path = request.app.state.attachment_storage.attachment_path(
        item.target_type, item.target_id, item.stored_name
    )
    session.delete(item)
    session.commit()
    path.unlink(missing_ok=True)
