from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.auth.dependencies import current_user
from app.auth.models import User
from app.database import get_session
from app.meetings.schemas import (
    AmendmentWrite,
    LifecycleCommand,
    MeetingEdit,
    MeetingSeriesEdit,
    MeetingSeriesWrite,
    MeetingWrite,
    OccurrenceWrite,
)
from app.meetings.service import MeetingService

router = APIRouter(tags=["meetings"])
# Kept as an empty compatibility router while v0.1 action routes are retired.
actions_router = APIRouter()


@router.get("/api/projects/{project_id}/meeting-series")
def list_series(
    project_id: str,
    _user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> list[dict[str, Any]]:
    return MeetingService(session).list_series(project_id)


@router.post("/api/projects/{project_id}/meeting-series", status_code=201)
def create_series(
    project_id: str,
    payload: MeetingSeriesWrite,
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    service = MeetingService(session)
    return service.serialize_series(service.create_series(project_id, payload, user))


@router.get("/api/meeting-series/{series_id}")
def get_series(
    series_id: str,
    _user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    return MeetingService(session).series_detail(series_id)


@router.put("/api/meeting-series/{series_id}")
def update_series(
    series_id: str,
    payload: MeetingSeriesEdit,
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    service = MeetingService(session)
    return service.serialize_series(service.update_series(series_id, payload, user))


@router.post("/api/meeting-series/{series_id}/occurrences", status_code=201)
def create_occurrence(
    series_id: str,
    payload: OccurrenceWrite,
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    service = MeetingService(session)
    return service.serialize_meeting(
        service.create_occurrence(series_id, payload, user)
    )


@router.get("/api/projects/{project_id}/meetings")
def list_meetings(
    project_id: str,
    _user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> list[dict[str, Any]]:
    return MeetingService(session).list_meetings(project_id)


@router.post("/api/projects/{project_id}/meetings", status_code=201)
def create_meeting(
    project_id: str,
    payload: MeetingWrite,
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    service = MeetingService(session)
    return service.serialize_meeting(service.create_meeting(project_id, payload, user))


@router.get("/api/meetings/{meeting_id}")
def get_meeting(
    meeting_id: str,
    _user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    return MeetingService(session).meeting_detail(meeting_id)


@router.put("/api/meetings/{meeting_id}")
def update_meeting(
    meeting_id: str,
    payload: MeetingEdit,
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    service = MeetingService(session)
    return service.serialize_meeting(service.update_meeting(meeting_id, payload, user))


def _lifecycle_result(
    operation: str,
    meeting_id: str,
    payload: LifecycleCommand,
    user: User,
    session: Session,
) -> dict[str, Any]:
    service = MeetingService(session)
    meeting = getattr(service, operation)(meeting_id, payload, user)
    return service.serialize_meeting(meeting)


@router.post("/api/meetings/{meeting_id}/ready")
def mark_ready(
    meeting_id: str,
    payload: LifecycleCommand,
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    return _lifecycle_result("mark_ready", meeting_id, payload, user, session)


@router.post("/api/meetings/{meeting_id}/start")
def start_meeting(
    meeting_id: str,
    payload: LifecycleCommand,
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    return _lifecycle_result("start", meeting_id, payload, user, session)


@router.post("/api/meetings/{meeting_id}/finish")
def finish_meeting(
    meeting_id: str,
    payload: LifecycleCommand,
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    return _lifecycle_result("finish", meeting_id, payload, user, session)


@router.post("/api/meetings/{meeting_id}/reopen")
def reopen_meeting(
    meeting_id: str,
    payload: LifecycleCommand,
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    return _lifecycle_result("reopen", meeting_id, payload, user, session)


@router.post("/api/meetings/{meeting_id}/cancel")
def cancel_meeting(
    meeting_id: str,
    payload: LifecycleCommand,
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    return _lifecycle_result("cancel", meeting_id, payload, user, session)


@router.get("/api/meetings/{meeting_id}/snapshots")
def list_snapshots(
    meeting_id: str,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    _user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> list[dict[str, Any]]:
    service = MeetingService(session)
    return [
        service.serialize_snapshot(row)
        for row in service.list_snapshots(meeting_id, limit=limit, offset=offset)
    ]


@router.post("/api/meetings/{meeting_id}/amendments", status_code=201)
def add_amendment(
    meeting_id: str,
    payload: AmendmentWrite,
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    service = MeetingService(session)
    return service.serialize_amendment(service.add_amendment(meeting_id, payload, user))
