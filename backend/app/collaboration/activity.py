from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.pagination import slice_page
from app.collaboration.models import ActivityEvent


@dataclass(frozen=True)
class ActivityPage:
    items: list[ActivityEvent]
    next_cursor: int | None


class ActivityRecorder:
    def __init__(self, session: Session):
        self.session = session

    def record(
        self,
        *,
        project_id: str | None,
        actor_user_id: str | None,
        event_type: str,
        subject_type: str,
        subject_id: str,
        meeting_id: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> ActivityEvent:
        event = ActivityEvent(
            project_id=project_id,
            meeting_id=meeting_id,
            actor_user_id=actor_user_id,
            event_type=event_type,
            subject_type=subject_type,
            subject_id=subject_id,
            payload_json=payload or {},
        )
        self.session.add(event)
        return event

    def list_for_project(
        self,
        project_id: str,
        *,
        before: int | None = None,
        limit: int = 50,
        meeting_id: str | None = None,
    ) -> ActivityPage:
        if not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100")
        filters = [ActivityEvent.project_id == project_id]
        if before is not None:
            filters.append(ActivityEvent.id < before)
        if meeting_id is not None:
            filters.append(ActivityEvent.meeting_id == meeting_id)
        rows = list(
            self.session.scalars(
                select(ActivityEvent)
                .where(*filters)
                .options(joinedload(ActivityEvent.actor))
                .order_by(ActivityEvent.id.desc())
                .limit(limit + 1)
            )
        )
        items, next_cursor, _ = slice_page(rows, limit=limit)
        return ActivityPage(items=items, next_cursor=next_cursor)
