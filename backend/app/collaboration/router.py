from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.auth.dependencies import current_user
from app.auth.models import User
from app.collaboration.activity import ActivityRecorder
from app.collaboration.models import ActivityEvent
from app.collaboration.schemas import ActivityItem, ActivityPageResponse
from app.database import get_session
from app.projects.service import ProjectService, user_ref

router = APIRouter(prefix="/api/projects", tags=["collaboration"])


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
