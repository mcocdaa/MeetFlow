from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth.dependencies import current_user
from app.auth.models import User
from app.database import get_session
from app.meetings.schemas import ActionWrite, MeetingWrite, UpdateWrite
from app.meetings.service import MeetingService

router = APIRouter(prefix="/api/meetings", tags=["meetings"])
actions_router = APIRouter(prefix="/api/actions", tags=["actions"])


@router.get("")
def list_meetings(
    q: str = "",
    _user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> list[dict[str, Any]]:
    return MeetingService(session).list_meetings(q)


@router.post("", status_code=201)
def create_meeting(
    payload: MeetingWrite,
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    return MeetingService(session).create(payload, user)


@router.get("/{meeting_id}")
def get_meeting(
    meeting_id: str,
    _user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    return MeetingService(session).package(meeting_id)


@router.put("/{meeting_id}")
def update_meeting(
    meeting_id: str,
    payload: MeetingWrite,
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    return MeetingService(session).update(meeting_id, payload, user)


@router.delete("/{meeting_id}", status_code=204)
def delete_meeting(
    meeting_id: str,
    _user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> None:
    MeetingService(session).delete(meeting_id)


@router.post("/{meeting_id}/actions", status_code=201)
def create_action(
    meeting_id: str,
    payload: ActionWrite,
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    return MeetingService(session).create_action(meeting_id, payload, user)


@router.put("/{meeting_id}/actions/{action_id}")
def update_action(
    meeting_id: str,
    action_id: str,
    payload: ActionWrite,
    _user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    return MeetingService(session).update_action(meeting_id, action_id, payload)


@router.delete("/{meeting_id}/actions/{action_id}", status_code=204)
def delete_action(
    meeting_id: str,
    action_id: str,
    _user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> None:
    MeetingService(session).delete_action(meeting_id, action_id)


@actions_router.get("")
def list_actions(
    status: str = "open",
    _user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> list[dict[str, Any]]:
    if status not in {"", "open", "done"}:
        return []
    return MeetingService(session).list_actions(status)


@router.post("/{meeting_id}/updates", status_code=201)
def create_update(
    meeting_id: str,
    payload: UpdateWrite,
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    return MeetingService(session).create_update(meeting_id, payload, user)


@router.delete("/{meeting_id}/updates/{update_id}", status_code=204)
def delete_update(
    meeting_id: str,
    update_id: str,
    _user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> None:
    MeetingService(session).delete_update(meeting_id, update_id)
