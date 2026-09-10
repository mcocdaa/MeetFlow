from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, joinedload

from app.agendas.models import AgendaItem
from app.domain.enums import MeetingStatus
from app.meetings.models import (
    Meeting,
    MeetingAmendment,
    MeetingParticipant,
    MeetingSnapshot,
)
from app.refs import project_ref, user_ref
from app.time_utils import as_utc


def query_meetings(
    session: Session,
    *,
    project_id: str | None = None,
    include_details: bool = False,
    status: MeetingStatus | None = None,
    participant_user_id: str | None = None,
    start_after: datetime | None = None,
    start_before: datetime | None = None,
    limit: int | None = None,
    offset: int = 0,
    visible_project_ids: list[str] | None = None,
    access_user_id: str | None = None,
) -> dict:
    """The single meeting-list query and row projection.

    Shared by the project-scoped list and the workspace-wide /api/meetings.
    """
    agenda_count = (
        select(func.count(AgendaItem.id))
        .where(AgendaItem.meeting_id == Meeting.id)
        .correlate(Meeting)
        .scalar_subquery()
    )
    snapshot_count = (
        select(func.count(MeetingSnapshot.id))
        .where(MeetingSnapshot.meeting_id == Meeting.id)
        .correlate(Meeting)
        .scalar_subquery()
    )
    amendment_count = (
        select(func.count(MeetingAmendment.id))
        .where(MeetingAmendment.meeting_id == Meeting.id)
        .correlate(Meeting)
        .scalar_subquery()
    )
    statement = select(Meeting, agenda_count, snapshot_count, amendment_count)
    count_statement = select(func.count()).select_from(Meeting)
    filters = []
    if visible_project_ids is not None and access_user_id is not None:
        participant_meeting_ids = select(MeetingParticipant.meeting_id).where(
            MeetingParticipant.user_id == access_user_id
        )
        filters.append(
            or_(
                Meeting.project_id.in_(visible_project_ids),
                Meeting.id.in_(participant_meeting_ids),
            )
        )
    if project_id is not None:
        filters.append(Meeting.project_id == project_id)
    if status is not None:
        filters.append(Meeting.status == status)
    if start_after is not None:
        filters.append(Meeting.scheduled_start >= start_after)
    if start_before is not None:
        filters.append(Meeting.scheduled_start <= start_before)
    if participant_user_id is not None:
        statement = statement.join(MeetingParticipant)
        count_statement = count_statement.join(MeetingParticipant)
        filters.append(MeetingParticipant.user_id == participant_user_id)
    rows = session.execute(
        statement.where(*filters)
        .options(
            joinedload(Meeting.project),
            joinedload(Meeting.series),
            joinedload(Meeting.host),
            joinedload(Meeting.recorder),
        )
        .order_by(Meeting.scheduled_start.desc(), Meeting.id)
        .limit(limit)
        .offset(offset)
    ).all()
    items = [
        {
            "id": meeting.id,
            "project": project_ref(meeting.project),
            "series": (
                {"id": meeting.series.id, "title": meeting.series.title}
                if meeting.series is not None
                else None
            ),
            "title": meeting.title,
            "occurrence_kind": meeting.occurrence_kind.value,
            "scheduled_start": as_utc(meeting.scheduled_start),
            "scheduled_end": as_utc(meeting.scheduled_end),
            "status": meeting.status,
            "host": user_ref(meeting.host),
            "recorder": user_ref(meeting.recorder),
            "version": meeting.version,
            "agenda_count": agendas,
            "snapshot_count": snapshots,
            "amendment_count": amendments,
            **(
                {
                    "purpose_markdown": meeting.purpose_markdown,
                    "updated_at": meeting.updated_at,
                }
                if include_details
                else {}
            ),
        }
        for meeting, agendas, snapshots, amendments in rows
    ]
    if limit is None:
        return {"items": items}
    return {
        "items": items,
        "total": session.scalar(count_statement.where(*filters)) or 0,
        "limit": limit,
        "offset": offset,
    }
