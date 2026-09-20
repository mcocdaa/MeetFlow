from datetime import datetime, timezone
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

router = APIRouter(prefix="/api/calendar", tags=["calendar"])
CALENDAR_SALT = "meetflow-calendar-feed-v1"


def get_serializer(request: Request) -> URLSafeSerializer:
    secret = getattr(request.app.state.settings, "app_secret_key", "default-meetflow-secret")
    return URLSafeSerializer(secret, salt=CALENDAR_SALT)


def generate_ics_feed(user: User, actions: list[ActionItem], meetings: list[Meeting]) -> str:
    now_stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//MeetFlow//Calendar//CN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:MeetFlow - {user.display_name}的待办日程",
        "X-WR-TIMEZONE:UTC",
    ]

    for action in actions:
        if not action.due_date:
            continue
        due_str = action.due_date.strftime("%Y%m%d")
        created_stamp = (action.created_at or datetime.now(timezone.utc)).strftime("%Y%m%dT%H%M%SZ")
        lines.extend([
            "BEGIN:VEVENT",
            f"UID:action-{action.id}@meetflow",
            f"DTSTAMP:{now_stamp}",
            f"CREATED:{created_stamp}",
            f"DTSTART;VALUE=DATE:{due_str}",
            f"DTEND;VALUE=DATE:{due_str}",
            f"SUMMARY:[待办] {action.content}",
            f"DESCRIPTION:状态: {action.status.value}\\n优先级: {action.priority.value}",
            "STATUS:CONFIRMED",
            "END:VEVENT",
        ])

    for meeting in meetings:
        if not meeting.scheduled_start:
            continue
        start_stamp = meeting.scheduled_start.strftime("%Y%m%dT%H%M%SZ")
        end_stamp = (
            meeting.scheduled_end.strftime("%Y%m%dT%H%M%SZ")
            if meeting.scheduled_end
            else start_stamp
        )
        created_stamp = (meeting.created_at or datetime.now(timezone.utc)).strftime("%Y%m%dT%H%M%SZ")
        purpose = (meeting.purpose_markdown or "").replace("\n", "\\n")
        lines.extend([
            "BEGIN:VEVENT",
            f"UID:meeting-{meeting.id}@meetflow",
            f"DTSTAMP:{now_stamp}",
            f"CREATED:{created_stamp}",
            f"DTSTART:{start_stamp}",
            f"DTEND:{end_stamp}",
            f"SUMMARY:[会议] {meeting.title}",
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
