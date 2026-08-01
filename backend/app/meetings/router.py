from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, Query
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
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
from app.projects.access import WorkspaceAccess

router = APIRouter(tags=["meetings"])


def _utc_content(value: Any) -> Any:
    if isinstance(value, datetime):
        utc_value = (
            value.replace(tzinfo=timezone.utc)
            if value.tzinfo is None or value.utcoffset() is None
            else value.astimezone(timezone.utc)
        )
        return utc_value.isoformat().replace("+00:00", "Z")
    if isinstance(value, dict):
        return {key: _utc_content(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_utc_content(item) for item in value]
    return value


def _utc_response(value: Any, *, status_code: int = 200) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content=jsonable_encoder(_utc_content(value)),
    )


def _meeting_payload(
    service: MeetingService, meeting, user: User
) -> dict[str, Any]:
    access = WorkspaceAccess(service.session)
    capabilities = access.meeting_capabilities(meeting, user)
    result = service.serialize_meeting(meeting)
    result["capabilities"] = {
        "can_manage": capabilities.can_manage,
        "can_contribute": capabilities.can_contribute,
        "can_comment": capabilities.can_comment,
    }
    return result


def _require_meeting_contribution(
    session: Session, meeting_id: str, user: User
):
    access = WorkspaceAccess(session)
    meeting = access.require_meeting_view(meeting_id, user)
    access.require_project_contribute(meeting.project_id, user)
    return meeting


@router.get("/api/projects/{project_id}/meeting-series")
def list_series(
    project_id: str,
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> list[dict[str, Any]]:
    WorkspaceAccess(session).require_project_view(project_id, user)
    return _utc_response(MeetingService(session).list_series(project_id))


@router.post("/api/projects/{project_id}/meeting-series", status_code=201)
def create_series(
    project_id: str,
    payload: MeetingSeriesWrite,
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    service = MeetingService(session)
    WorkspaceAccess(session).require_project_contribute(project_id, user)
    return _utc_response(
        service.serialize_series(service.create_series(project_id, payload, user)),
        status_code=201,
    )


@router.get("/api/meeting-series/{series_id}")
def get_series(
    series_id: str,
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    service = MeetingService(session)
    series = service.get_series(series_id)
    WorkspaceAccess(session).require_project_view(series.project_id, user)
    return _utc_response(service.series_detail(series_id))


@router.put("/api/meeting-series/{series_id}")
def update_series(
    series_id: str,
    payload: MeetingSeriesEdit,
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    service = MeetingService(session)
    series = service.get_series(series_id)
    WorkspaceAccess(session).require_project_contribute(series.project_id, user)
    return _utc_response(service.serialize_series(service.update_series(series_id, payload, user)))


@router.post("/api/meeting-series/{series_id}/occurrences", status_code=201)
def create_occurrence(
    series_id: str,
    payload: OccurrenceWrite,
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    service = MeetingService(session)
    series = service.get_series(series_id)
    WorkspaceAccess(session).require_project_contribute(series.project_id, user)
    return _utc_response(
        service.serialize_meeting(service.create_occurrence(series_id, payload, user)),
        status_code=201,
    )


@router.get("/api/projects/{project_id}/meetings")
def list_meetings(
    project_id: str,
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> list[dict[str, Any]]:
    WorkspaceAccess(session).require_project_view(project_id, user)
    return _utc_response(MeetingService(session).list_meetings(project_id))


@router.post("/api/projects/{project_id}/meetings", status_code=201)
def create_meeting(
    project_id: str,
    payload: MeetingWrite,
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    service = MeetingService(session)
    WorkspaceAccess(session).require_project_contribute(project_id, user)
    meeting = service.create_meeting(project_id, payload, user)
    return _utc_response(
        _meeting_payload(service, meeting, user),
        status_code=201,
    )


@router.get("/api/meetings/{meeting_id}")
def get_meeting(
    meeting_id: str,
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    service = MeetingService(session)
    meeting = WorkspaceAccess(session).require_meeting_view(meeting_id, user)
    result = service.meeting_detail(meeting_id, user)
    capabilities = WorkspaceAccess(session).meeting_capabilities(meeting, user)
    result["capabilities"] = {
        "can_manage": capabilities.can_manage,
        "can_contribute": capabilities.can_contribute,
        "can_comment": capabilities.can_comment,
    }
    return _utc_response(result)


@router.put("/api/meetings/{meeting_id}")
def update_meeting(
    meeting_id: str,
    payload: MeetingEdit,
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    service = MeetingService(session)
    _require_meeting_contribution(session, meeting_id, user)
    meeting = service.update_meeting(meeting_id, payload, user)
    return _utc_response(_meeting_payload(service, meeting, user))


def _lifecycle_result(
    operation: str,
    meeting_id: str,
    payload: LifecycleCommand,
    user: User,
    session: Session,
) -> JSONResponse:
    service = MeetingService(session)
    _require_meeting_contribution(session, meeting_id, user)
    meeting = getattr(service, operation)(meeting_id, payload, user)
    return _utc_response(_meeting_payload(service, meeting, user))


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
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> list[dict[str, Any]]:
    service = MeetingService(session)
    WorkspaceAccess(session).require_meeting_view(meeting_id, user)
    return _utc_response([
        service.serialize_snapshot(row)
        for row in service.list_snapshots(meeting_id, limit=limit, offset=offset)
    ])


@router.post("/api/meetings/{meeting_id}/amendments", status_code=201)
def add_amendment(
    meeting_id: str,
    payload: AmendmentWrite,
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    service = MeetingService(session)
    _require_meeting_contribution(session, meeting_id, user)
    return _utc_response(
        service.serialize_amendment(service.add_amendment(meeting_id, payload, user)),
        status_code=201,
    )
