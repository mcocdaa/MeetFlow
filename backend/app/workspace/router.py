from datetime import date, datetime
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select
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
from app.http import utc_response
from app.meetings.models import (
    Meeting,
    MeetingAmendment,
    MeetingParticipant,
    MeetingSnapshot,
)
from app.meetings.queries import MeetingQueries
from app.meetings.service import MeetingService
from app.outcomes.models import ActionItem, Decision, DecisionReviewer
from app.outcomes.service import OutcomeService
from app.projects.access import WorkspaceAccess
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
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    filters = []
    visible_project_ids = WorkspaceAccess(session).visible_project_ids(user)
    if visible_project_ids is not None:
        filters.append(ActionItem.project_id.in_(visible_project_ids))
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
    return utc_response(page)


@router.get("/api/decisions")
def global_decisions(
    project_id: str | None = None,
    status: DecisionStatus | None = None,
    reviewer_user_id: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    statement = select(Decision).options(selectinload(Decision.reviewers))
    count_statement = select(func.count()).select_from(Decision)
    filters = []
    visible_project_ids = WorkspaceAccess(session).visible_project_ids(user)
    if visible_project_ids is not None:
        filters.append(Decision.project_id.in_(visible_project_ids))
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
    return utc_response(page)


@router.get("/api/meetings")
def global_meetings(
    project_id: str | None = None,
    status: MeetingStatus | None = None,
    participant_user_id: str | None = None,
    start_after: datetime | None = None,
    start_before: datetime | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    visible_project_ids = WorkspaceAccess(session).visible_project_ids(user)
    page = MeetingQueries(MeetingService(session)).list_meetings(
        include_details=True,
        status=status,
        participant_user_id=participant_user_id,
        start_after=start_after,
        start_before=start_before,
        limit=limit,
        offset=offset,
        visible_project_ids=visible_project_ids,
        access_user_id=user.id,
    )
    return utc_response(page)


@router.get("/api/attention")
def attention(
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
):
    return utc_response(AttentionService(session).for_user(user))


@router.get("/api/work-brief")
def work_brief(
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
):
    return utc_response(current_work_brief(session, user.id))
