from datetime import date, datetime
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.agendas.models import AgendaItem
from app.attention.service import AttentionService
from app.auth.dependencies import current_user
from app.auth.models import User
from app.database import get_session
from app.domain.enums import (
    ActionStatus,
    DecisionStatus,
    MeetingStatus,
)
from app.meetings.models import (
    Meeting,
    MeetingAmendment,
    MeetingParticipant,
    MeetingSnapshot,
)
from app.meetings.service import as_utc, project_ref, user_ref
from app.outcomes.models import ActionItem, Decision, DecisionReviewer
from app.outcomes.service import OutcomeService
from app.workspace.work_briefs import current_work_brief

router = APIRouter(tags=["workspace"])


def _page(session: Session, statement, count_statement, limit: int, offset: int):
    return {
        "items": list(session.scalars(statement.limit(limit).offset(offset))),
        "total": session.scalar(count_statement) or 0,
        "limit": limit,
        "offset": offset,
    }


@router.get("/api/actions")
def global_actions(
    project_id: str | None = None,
    status: ActionStatus | None = None,
    owner_user_id: str | None = None,
    due_before: date | None = None,
    due_after: date | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    _user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    filters = []
    if project_id:
        filters.append(ActionItem.project_id == project_id)
    if status:
        filters.append(ActionItem.status == status)
    if owner_user_id:
        filters.append(ActionItem.owner_user_id == owner_user_id)
    if due_before:
        filters.append(ActionItem.due_date <= due_before)
    if due_after:
        filters.append(ActionItem.due_date >= due_after)
    page = _page(
        session,
        select(ActionItem)
        .where(*filters)
        .order_by(ActionItem.due_date, ActionItem.updated_at.desc(), ActionItem.id),
        select(func.count()).select_from(ActionItem).where(*filters),
        limit,
        offset,
    )
    page["items"] = [OutcomeService.serialize(row) for row in page["items"]]
    return page


@router.get("/api/decisions")
def global_decisions(
    project_id: str | None = None,
    status: DecisionStatus | None = None,
    reviewer_user_id: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    _user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    statement = select(Decision).options(selectinload(Decision.reviewers))
    count_statement = select(func.count()).select_from(Decision)
    filters = []
    if project_id:
        filters.append(Decision.project_id == project_id)
    if status:
        filters.append(Decision.status == status)
    if reviewer_user_id:
        statement = statement.join(DecisionReviewer)
        count_statement = count_statement.join(DecisionReviewer)
        filters.append(DecisionReviewer.user_id == reviewer_user_id)
    page = _page(
        session,
        statement.where(*filters).order_by(Decision.updated_at.desc(), Decision.id),
        count_statement.where(*filters),
        limit,
        offset,
    )
    page["items"] = [OutcomeService.serialize(row) for row in page["items"]]
    return page


@router.get("/api/meetings")
def global_meetings(
    project_id: str | None = None,
    status: MeetingStatus | None = None,
    participant_user_id: str | None = None,
    start_after: datetime | None = None,
    start_before: datetime | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    _user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
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
    if project_id:
        filters.append(Meeting.project_id == project_id)
    if status:
        filters.append(Meeting.status == status)
    if start_after:
        filters.append(Meeting.scheduled_start >= start_after)
    if start_before:
        filters.append(Meeting.scheduled_start <= start_before)
    if participant_user_id:
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
            "purpose_markdown": meeting.purpose_markdown,
            "scheduled_start": as_utc(meeting.scheduled_start),
            "scheduled_end": as_utc(meeting.scheduled_end),
            "status": meeting.status,
            "host": user_ref(meeting.host),
            "recorder": user_ref(meeting.recorder),
            "version": meeting.version,
            "agenda_count": agendas,
            "snapshot_count": snapshots,
            "amendment_count": amendments,
            "updated_at": meeting.updated_at,
        }
        for meeting, agendas, snapshots, amendments in rows
    ]
    return {
        "items": items,
        "total": session.scalar(count_statement.where(*filters)) or 0,
        "limit": limit,
        "offset": offset,
    }


@router.get("/api/attention")
def attention(
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    return AttentionService(session).for_user(user)


@router.get("/api/work-brief")
def work_brief(
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    return current_work_brief(session, user.id)
