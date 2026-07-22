from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.auth.dependencies import current_user
from app.auth.models import User
from app.database import get_session
from app.inbox.schemas import InboxChangesResponse, InboxHistoryResponse
from app.inbox.service import InboxService

router = APIRouter(prefix="/api/inbox", tags=["inbox"])


@router.get("", response_model=InboxHistoryResponse)
def inbox_history(
    before: int | None = Query(default=None, ge=1),
    limit: int = Query(default=50, ge=1, le=100),
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> dict:
    service = InboxService(session)
    page = service.history(user.id, before=before, limit=limit)
    return {
        "items": [service.serialize(item) for item in page.items],
        "next_cursor": page.next_cursor,
        "unread_count": service.unread_count(user.id),
    }


@router.get("/changes", response_model=InboxChangesResponse)
def inbox_changes(
    cursor: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> dict:
    service = InboxService(session)
    page = service.changes(user.id, cursor=cursor, limit=limit)
    return {
        "notifications": [service.serialize(item) for item in page.items],
        "next_cursor": page.next_cursor,
        "has_more": page.has_more,
        "unread_count": service.unread_count(user.id),
    }


@router.post("/read-all", status_code=204)
def read_all_notifications(
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> None:
    InboxService(session).read_all(user.id)


@router.post("/{notification_id}/read", status_code=204)
def read_notification(
    notification_id: int,
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> None:
    InboxService(session).read(notification_id, user.id)
