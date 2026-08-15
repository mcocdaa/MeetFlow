from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import joinedload

from app.agendas.models import AgendaItem
from app.auth.models import User
from app.domain.enums import MeetingStatus
from app.meetings.models import (
    Meeting,
    MeetingAmendment,
    MeetingParticipant,
    MeetingSnapshot,
)
from app.refs import project_ref, user_ref
from app.time_utils import as_utc

if TYPE_CHECKING:
    from app.meetings.service import MeetingService


class MeetingQueries:
    """Read-side boundary: every meeting read path funnels through here."""

    def __init__(self, service: MeetingService):
        self.service = service

    @property
    def session(self):
        return self.service.session

    def list_meetings(
        self,
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
        rows = self.session.execute(
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
            "total": self.session.scalar(count_statement.where(*filters)) or 0,
            "limit": limit,
            "offset": offset,
        }

    def list_series(self, project_id: str) -> list[dict[str, Any]]:
        return self.service._list_series_impl(project_id)

    def series_detail(self, series_id: str) -> dict[str, Any]:
        return self.service._series_detail_impl(series_id)

    def meeting_detail(
        self, meeting_id: str, actor: User | None = None
    ) -> dict[str, Any]:
        return self.service._meeting_detail_impl(meeting_id, actor)

    def package(self, meeting_id: str) -> dict[str, Any]:
        return self.service._package_impl(meeting_id)

    def plugin_context(self, meeting_id: str, user: User) -> dict[str, Any]:
        return self.service._plugin_context_impl(meeting_id, user)
