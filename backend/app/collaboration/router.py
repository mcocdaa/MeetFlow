from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.auth.dependencies import current_user
from app.auth.models import User
from app.collaboration.activity import ActivityRecorder
from app.collaboration.models import ActivityEvent
from app.collaboration.schemas import (
    ActivityItem,
    ActivityPageResponse,
    CommentCommand,
    CommentEdit,
    CommentWrite,
)
from app.collaboration.service import CommentService
from app.database import get_session
from app.projects.service import ProjectService, user_ref

router = APIRouter(prefix="/api/projects", tags=["collaboration"])
comments_router = APIRouter(prefix="/api/comments", tags=["comments"])


def _serialize(item: ActivityEvent) -> ActivityItem:
    return ActivityItem(
        id=item.id,
        project_id=item.project_id,
        meeting_id=item.meeting_id,
        actor=user_ref(item.actor),
        event_type=item.event_type,
        subject={"type": item.subject_type, "id": item.subject_id},
        payload=item.payload_json,
        created_at=item.created_at,
    )


@router.get("/{project_id}/activity", response_model=ActivityPageResponse)
def list_project_activity(
    project_id: str,
    before: int | None = Query(default=None, ge=1),
    limit: int = Query(default=50, ge=1, le=100),
    meeting_id: str | None = Query(default=None),
    _user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> ActivityPageResponse:
    ProjectService(session).require(project_id)
    page = ActivityRecorder(session).list_for_project(
        project_id, before=before, limit=limit, meeting_id=meeting_id
    )
    return ActivityPageResponse(
        items=[_serialize(item) for item in page.items],
        next_cursor=page.next_cursor,
    )


@comments_router.get("")
def list_comments(
    target_type: str = Query(min_length=1, max_length=40),
    target_id: str = Query(min_length=1, max_length=36),
    before: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=50),
    reply_limit: int = Query(default=50, ge=1, le=100),
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> dict:
    service = CommentService(session)
    page = service.list_for_target(
        target_type,
        target_id,
        before=before,
        limit=limit,
        reply_limit=reply_limit,
    )
    return {
        "items": [
            service.serialize(
                comment,
                user,
                replies=page.replies_by_parent[comment.id],
                reply_next_cursor=page.reply_next_cursor_by_parent[comment.id],
            )
            for comment in page.items
        ],
        "next_cursor": page.next_cursor,
    }


@comments_router.get("/{comment_id}/replies")
def list_comment_replies(
    comment_id: str,
    after: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> dict:
    service = CommentService(session)
    page = service.list_replies(comment_id, after=after, limit=limit)
    return {
        "items": [service.serialize(comment, user) for comment in page.items],
        "next_cursor": page.next_cursor,
    }


@comments_router.post("", status_code=201)
def create_comment(
    payload: CommentWrite,
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> dict:
    service = CommentService(session)
    return service.serialize(service.create(payload, user), user)


@comments_router.put("/{comment_id}")
def update_comment(
    comment_id: str,
    payload: CommentEdit,
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> dict:
    service = CommentService(session)
    return service.serialize(service.update(comment_id, payload, user), user)


@comments_router.delete("/{comment_id}", status_code=204)
def delete_comment(
    comment_id: str,
    payload: CommentCommand,
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> None:
    CommentService(session).delete(comment_id, payload, user)
