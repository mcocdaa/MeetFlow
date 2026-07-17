from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, Request, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.attachments.storage import INLINE_IMAGES, sniff_inline_image
from app.auth.dependencies import current_user
from app.auth.models import User
from app.database import get_session
from app.errors import AppError
from app.meetings.models import Attachment
from app.meetings.service import MeetingService

router = APIRouter(
    prefix="/api/meetings/{meeting_id}/attachments", tags=["attachments"]
)


def require_attachment(
    session: Session, meeting_id: str, attachment_id: str
) -> Attachment:
    attachment = session.scalar(
        select(Attachment).where(
            Attachment.id == attachment_id,
            Attachment.meeting_id == meeting_id,
        )
    )
    if not attachment:
        raise AppError(404, "attachment_not_found", "附件不存在")
    return attachment


@router.post("", status_code=201)
async def upload_attachment(
    meeting_id: str,
    request: Request,
    file: UploadFile = File(...),
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    service = MeetingService(session)
    service.require(meeting_id)
    storage = request.app.state.attachment_storage
    stored_name, final_path, size = await storage.save(meeting_id, file)
    detected_image = sniff_inline_image(final_path)
    client_mime = (file.content_type or "application/octet-stream")[:160]
    mime_type = detected_image or client_mime
    attachment = Attachment(
        meeting_id=meeting_id,
        original_name=Path(file.filename or "file").name[:255],
        stored_name=stored_name,
        mime_type=mime_type,
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
    return service.serialize_attachment(attachment)


@router.get("/{attachment_id}")
def download_attachment(
    meeting_id: str,
    attachment_id: str,
    request: Request,
    _user: User = Depends(current_user),
    session: Session = Depends(get_session),
):
    attachment = require_attachment(session, meeting_id, attachment_id)
    path = request.app.state.attachment_storage.attachment_path(
        meeting_id, attachment.stored_name
    )
    if not path.is_file():
        raise AppError(404, "attachment_file_missing", "附件文件不存在")
    disposition = (
        "inline" if attachment.mime_type in INLINE_IMAGES else "attachment"
    )
    return FileResponse(
        path,
        media_type=attachment.mime_type,
        filename=attachment.original_name,
        content_disposition_type=disposition,
    )


@router.delete("/{attachment_id}", status_code=204)
def delete_attachment(
    meeting_id: str,
    attachment_id: str,
    request: Request,
    _user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> None:
    attachment = require_attachment(session, meeting_id, attachment_id)
    path = request.app.state.attachment_storage.attachment_path(
        meeting_id, attachment.stored_name
    )
    session.delete(attachment)
    session.commit()
    path.unlink(missing_ok=True)
