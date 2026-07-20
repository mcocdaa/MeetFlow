from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth.dependencies import current_user
from app.auth.models import User
from app.database import get_session
from app.meetings.schemas import (
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
