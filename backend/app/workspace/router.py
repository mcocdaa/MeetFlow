from datetime import date, datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.agendas.models import AgendaItem
from app.auth.dependencies import current_user
from app.auth.models import User
from app.database import get_session
from app.domain.enums import (
    ActionStatus,
    DecisionReviewerStatus,
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
from app.projects.models import Project

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


def _attention_item(
    subject_type: str,
    subject_id: str,
    project: Project,
    title: str,
    reason: str,
    **values,
) -> dict[str, Any]:
    return {
        "subject_type": subject_type,
        "subject_id": subject_id,
        "project": {"id": project.id, "name": project.name, "slug": project.slug},
        "title": title,
        "reasons": [reason],
        **values,
    }


@router.get("/api/attention")
def attention(
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    today = datetime.now(timezone.utc).date()
    horizon = today + timedelta(days=7)
    rows: dict[tuple[str, str], dict[str, Any]] = {}

    actions = session.scalars(
        select(ActionItem)
        .where(
            ActionItem.owner_user_id == user.id,
            ActionItem.status.in_([ActionStatus.open, ActionStatus.in_progress]),
            ActionItem.due_date.is_not(None),
            ActionItem.due_date <= horizon,
        )
        .options(joinedload(ActionItem.project))
    )
    for action in actions:
        reason = "action_overdue" if action.due_date < today else "action_due_soon"
        rows[("action", action.id)] = _attention_item(
            "action",
            action.id,
            action.project,
            action.content,
            reason,
            due_date=action.due_date,
            status=action.status,
        )

    decisions = session.scalars(
        select(Decision)
        .join(DecisionReviewer)
        .where(
            DecisionReviewer.user_id == user.id,
            DecisionReviewer.status == DecisionReviewerStatus.pending,
            Decision.status == DecisionStatus.proposed,
        )
        .options(joinedload(Decision.project))
    )
    for decision in decisions:
        rows[("decision", decision.id)] = _attention_item(
            "decision",
            decision.id,
            decision.project,
            decision.title,
            "decision_review_pending",
            status=decision.status,
        )

    now = datetime.now(timezone.utc)
    upcoming = now + timedelta(days=7)
    meetings = session.scalars(
        select(Meeting)
        .outerjoin(MeetingParticipant)
        .where(
            Meeting.scheduled_start >= now,
            Meeting.scheduled_start <= upcoming,
            Meeting.status.in_([MeetingStatus.draft, MeetingStatus.ready]),
            (
                (Meeting.host_user_id == user.id)
                | (Meeting.recorder_user_id == user.id)
                | (MeetingParticipant.user_id == user.id)
            ),
        )
        .options(joinedload(Meeting.project), selectinload(Meeting.agenda_items))
        .distinct()
    )
    for meeting in meetings:
        key = ("meeting", meeting.id)
        row = _attention_item(
            "meeting",
            meeting.id,
            meeting.project,
            meeting.title,
            "meeting_upcoming",
            scheduled_start=meeting.scheduled_start,
            status=meeting.status,
        )
        if meeting.status in {MeetingStatus.draft, MeetingStatus.ready} and any(
            item.status.value in {"planned", "in_progress"}
            for item in meeting.agenda_items
        ):
            row["reasons"].append("meeting_needs_preparation")
        rows[key] = row

    order = {"action": 0, "decision": 1, "meeting": 2}
    items = sorted(
        rows.values(), key=lambda item: (order[item["subject_type"]], item["title"])
    )
    return {"items": items, "notifications": [], "mentions": []}
