from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, Request, Response
from itsdangerous import BadSignature, SignatureExpired, URLSafeSerializer
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.auth.dependencies import current_user
from app.auth.models import User, UserStatus
from app.database import get_session
from app.domain.enums import ActionStatus, MeetingStatus
from app.errors import AppError
from app.meetings.models import Meeting, MeetingParticipant
from app.outcomes.models import ActionItem
from app.time_utils import as_utc

router = APIRouter(prefix="/api/calendar", tags=["calendar"])
CALENDAR_SALT = "meetflow-calendar-feed-v1"


def get_serializer(request: Request) -> URLSafeSerializer:
    secret = getattr(request.app.state.settings, "app_secret_key", "default-meetflow-secret")
    return URLSafeSerializer(secret, salt=CALENDAR_SALT)


def _escape_ics_text(value: str) -> str:
    return (
        value.replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\r\n", "\\n")
        .replace("\r", "\\n")
        .replace("\n", "\\n")
    )


def _utc_stamp(value: datetime | None) -> str:
    target = as_utc(value) if value is not None else datetime.now(timezone.utc)
    return target.strftime("%Y%m%dT%H%M%SZ")


def generate_ics_feed(user: User, actions: list[ActionItem], meetings: list[Meeting]) -> str:
    now_stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//MeetFlow//Calendar//CN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:MeetFlow - {_escape_ics_text(user.display_name)}的待办日程",
        "X-WR-TIMEZONE:UTC",
    ]

    for action in actions:
        if not action.due_date:
            continue
        due_start_str = action.due_date.strftime("%Y%m%d")
        due_end_str = (action.due_date + timedelta(days=1)).strftime("%Y%m%d")
        created_stamp = _utc_stamp(action.created_at)
        summary = _escape_ics_text(f"[待办] {action.content}")
        description = (
            f"状态: {_escape_ics_text(action.status.value)}\\n"
            f"优先级: {_escape_ics_text(action.priority.value)}"
        )
        lines.extend([
            "BEGIN:VEVENT",
            f"UID:action-{action.id}@meetflow",
            f"DTSTAMP:{now_stamp}",
            f"CREATED:{created_stamp}",
            f"DTSTART;VALUE=DATE:{due_start_str}",
            f"DTEND;VALUE=DATE:{due_end_str}",
            f"SUMMARY:{summary}",
            f"DESCRIPTION:{description}",
            "STATUS:CONFIRMED",
            "END:VEVENT",
        ])

    for meeting in meetings:
        if not meeting.scheduled_start:
            continue
        start_stamp = _utc_stamp(meeting.scheduled_start)
        end_stamp = (
            _utc_stamp(meeting.scheduled_end)
            if meeting.scheduled_end
            else start_stamp
        )
        created_stamp = _utc_stamp(meeting.created_at)
        summary = _escape_ics_text(f"[会议] {meeting.title}")
        purpose = _escape_ics_text(meeting.purpose_markdown or "")
        lines.extend([
            "BEGIN:VEVENT",
            f"UID:meeting-{meeting.id}@meetflow",
            f"DTSTAMP:{now_stamp}",
            f"CREATED:{created_stamp}",
            f"DTSTART:{start_stamp}",
            f"DTEND:{end_stamp}",
            f"SUMMARY:{summary}",
            f"DESCRIPTION:会议议题与目的:\\n{purpose}",
            "STATUS:CONFIRMED",
            "END:VEVENT",
        ])

    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"


@router.get("/feed-url")
def get_calendar_feed_url(
    request: Request,
    user: User = Depends(current_user),
) -> dict[str, Any]:
    serializer = get_serializer(request)
    token = serializer.dumps({"uid": user.id})
    feed_url = f"/api/calendar/{token}.ics"
    return {
        "token": token,
        "feed_url": feed_url,
    }


@router.get("/{token}.ics")
def export_calendar_ics(
    token: str,
    request: Request,
    session: Session = Depends(get_session),
) -> Response:
    serializer = get_serializer(request)
    try:
        data = serializer.loads(token)
        user_id = data.get("uid")
    except (BadSignature, SignatureExpired):
        raise AppError(404, "calendar_token_invalid", "日历订阅令牌无效或已过期")

    user = session.get(User, user_id)
    if not user or user.status != UserStatus.ACTIVE:
        raise AppError(404, "user_not_found", "用户不存在或已被禁用")

    actions = list(
        session.scalars(
            select(ActionItem)
            .where(
                ActionItem.owner_user_id == user.id,
                ActionItem.due_date.isnot(None),
                ActionItem.status.in_([ActionStatus.open, ActionStatus.in_progress]),
            )
            .order_by(ActionItem.due_date.asc())
        )
    )

    participant_meetings = list(
        session.scalars(
            select(Meeting)
            .join(MeetingParticipant, MeetingParticipant.meeting_id == Meeting.id)
            .where(
                MeetingParticipant.user_id == user.id,
                Meeting.status.in_([MeetingStatus.draft, MeetingStatus.ready, MeetingStatus.in_progress]),
                Meeting.scheduled_start.isnot(None),
            )
            .order_by(Meeting.scheduled_start.asc())
        )
    )

    ics_body = generate_ics_feed(user, actions, participant_meetings)
    return Response(
        content=ics_body,
        media_type="text/calendar; charset=utf-8",
        headers={
            "Content-Disposition": f"inline; filename=meetflow-{user.username}.ics",
            "Cache-Control": "no-cache, no-store, must-revalidate",
        },
    )
