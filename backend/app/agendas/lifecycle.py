from __future__ import annotations

from datetime import datetime, timezone

from app.agendas.models import AgendaItem
from app.domain.enums import AgendaStatus


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def actual_duration_seconds(item: AgendaItem, finished_at: datetime) -> int:
    if item.started_at is None:
        return 0
    return max(
        0,
        int((_as_utc(finished_at) - _as_utc(item.started_at)).total_seconds()),
    )


def start_planned_item(item: AgendaItem, *, actor_id: str, at: datetime) -> None:
    item.status = AgendaStatus.in_progress
    item.started_at = at
    item.completed_at = None
    item.actual_duration_seconds = None
    item.updated_by = actor_id
    item.version += 1


def complete_item(item: AgendaItem, *, actor_id: str, at: datetime) -> None:
    item.started_at = item.started_at or at
    item.status = AgendaStatus.completed
    item.completed_at = at
    item.actual_duration_seconds = actual_duration_seconds(item, at)
    item.updated_by = actor_id
    item.version += 1
