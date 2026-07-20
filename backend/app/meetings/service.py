from __future__ import annotations

from typing import Any, Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload, selectinload
from sqlalchemy.orm.exc import StaleDataError

from app.auth.models import User, UserStatus
from app.domain.versioning import require_version
from app.errors import AppError
from app.meetings.models import (
    ActionItem,
    Attachment,
    Meeting,
    MeetingParticipant,
    MeetingSeries,
    MeetingUpdate,
    SeriesParticipant,
    StandingAgendaItem,
)
from app.meetings.schemas import (
    MeetingEdit,
    MeetingSeriesEdit,
    MeetingSeriesWrite,
    MeetingWrite,
    OccurrenceWrite,
    ParticipantWrite,
    StandingAgendaWrite,
)
from app.projects.models import Project


def user_ref(user: User | None) -> dict[str, str] | None:
    if user is None:
        return None
    return {"id": user.id, "username": user.username, "display_name": user.display_name}


def project_ref(project: Project) -> dict[str, str]:
    return {"id": project.id, "name": project.name, "slug": project.slug}


def dedupe_participants(values: Iterable[ParticipantWrite]) -> list[ParticipantWrite]:
    """Keep the first occurrence, including its role and original relative order."""
    result: list[ParticipantWrite] = []
    seen: set[str] = set()
    for value in values:
        if value.user_id not in seen:
            seen.add(value.user_id)
            result.append(value)
    return result


class MeetingService:
    def __init__(self, session: Session):
        self.session = session

    @staticmethod
    def _require_active(actor: User) -> None:
        if actor.status != UserStatus.ACTIVE:
            raise AppError(403, "active_user_required", "账号尚未启用")

    def _project(self, project_id: str) -> Project:
        project = self.session.get(Project, project_id)
        if project is None:
            raise AppError(404, "project_not_found", "项目不存在")
        return project

    def _users(self, user_ids: Iterable[str | None]) -> dict[str, User]:
        ids = list(dict.fromkeys(user_id for user_id in user_ids if user_id))
        if not ids:
            return {}
        users = {
            user.id: user
            for user in self.session.scalars(select(User).where(User.id.in_(ids)))
        }
        missing = [user_id for user_id in ids if user_id not in users]
        if missing:
            raise AppError(
                422,
                "user_not_found",
                "会议参与人不存在",
                details={"user_ids": missing},
            )
        return users

    def get_series(self, series_id: str) -> MeetingSeries:
        series = self.session.get(MeetingSeries, series_id)
        if series is None:
            raise AppError(404, "meeting_series_not_found", "会议系列不存在")
        return series

    def get_meeting(self, meeting_id: str) -> Meeting:
        meeting = self.session.get(Meeting, meeting_id)
        if meeting is None:
            raise AppError(404, "meeting_not_found", "会议不存在")
        return meeting

    # Transitional name used by attachment/plugin integration.
    require = get_meeting

    @staticmethod
    def _series_participants(values: list[ParticipantWrite]) -> list[SeriesParticipant]:
        return [
            SeriesParticipant(
                user_id=value.user_id,
                participation_role=value.participation_role,
                position=position,
            )
            for position, value in enumerate(dedupe_participants(values))
        ]

    @staticmethod
    def _meeting_participants(values: list[ParticipantWrite]) -> list[MeetingParticipant]:
        return [
            MeetingParticipant(
                user_id=value.user_id,
                participation_role=value.participation_role,
                position=position,
            )
            for position, value in enumerate(dedupe_participants(values))
        ]

    @staticmethod
    def _standing_items(values: list[StandingAgendaWrite]) -> list[StandingAgendaItem]:
        return [
            StandingAgendaItem(**value.model_dump(), position=position)
            for position, value in enumerate(values)
        ]

    def _validate_series_references(
        self,
        *,
        host_id: str | None,
        recorder_id: str | None,
        participants: list[ParticipantWrite],
        standing_items: list[StandingAgendaWrite],
    ) -> None:
        self._users(
            [host_id, recorder_id]
            + [value.user_id for value in participants]
            + [value.default_owner_user_id for value in standing_items]
        )

    def create_series(
        self, project_id: str, payload: MeetingSeriesWrite, actor: User
    ) -> MeetingSeries:
        self._require_active(actor)
        self._project(project_id)
        participants = dedupe_participants(payload.participants)
        self._validate_series_references(
            host_id=payload.default_host_user_id,
            recorder_id=payload.default_recorder_user_id,
            participants=participants,
            standing_items=payload.standing_items,
        )
        values = payload.model_dump(exclude={"participants", "standing_items"})
        series = MeetingSeries(
            project_id=project_id,
            **values,
            version=1,
            created_by=actor.id,
            updated_by=actor.id,
            participants=self._series_participants(participants),
            standing_items=self._standing_items(payload.standing_items),
        )
        self.session.add(series)
        self.session.commit()
        self.session.refresh(series)
        return series

    def _raise_series_stale(self, series_id: str, expected_version: int, exc: Exception):
        self.session.rollback()
        actual = self.session.scalar(select(MeetingSeries.version).where(MeetingSeries.id == series_id))
        if actual is None:
            raise AppError(404, "meeting_series_not_found", "会议系列不存在") from exc
        require_version(expected_version, actual)
        raise AppError(409, "version_conflict", "会议系列已更新，请刷新后重试") from exc

    def update_series(
        self, series_id: str, payload: MeetingSeriesEdit, actor: User
    ) -> MeetingSeries:
        self._require_active(actor)
        series = self.get_series(series_id)
        require_version(payload.expected_version, series.version)
        changes = payload.model_dump(
            exclude={"expected_version", "participants", "standing_items"},
            exclude_unset=True,
        )
        if not changes and payload.participants is None and payload.standing_items is None:
            return series

        participants = payload.participants
        if participants is None:
            participants = [
                ParticipantWrite(user_id=row.user_id, participation_role=row.participation_role)
                for row in series.participants
            ]
        participants = dedupe_participants(participants)
        standing_items = payload.standing_items
        if standing_items is None:
            standing_items = [
                StandingAgendaWrite(
                    title=row.title,
                    agenda_type=row.agenda_type,
                    default_owner_user_id=row.default_owner_user_id,
                    default_duration_minutes=row.default_duration_minutes,
                )
                for row in series.standing_items
            ]
        self._validate_series_references(
            host_id=changes.get("default_host_user_id", series.default_host_user_id),
            recorder_id=changes.get("default_recorder_user_id", series.default_recorder_user_id),
            participants=participants,
            standing_items=standing_items,
        )
        for field, value in changes.items():
            setattr(series, field, value)
        if payload.participants is not None:
            series.participants = self._series_participants(participants)
        if payload.standing_items is not None:
            series.standing_items = self._standing_items(standing_items)
        series.updated_by = actor.id
        series.version += 1
        try:
            self.session.commit()
        except StaleDataError as exc:
            self._raise_series_stale(series_id, payload.expected_version, exc)
        self.session.refresh(series)
        return series

    def create_occurrence(
        self, series_id: str, payload: OccurrenceWrite, actor: User
    ) -> Meeting:
        self._require_active(actor)
        series = self.get_series(series_id)
        participants = [
            ParticipantWrite(user_id=row.user_id, participation_role=row.participation_role)
            for row in series.participants
        ]
        meeting = Meeting(
            project_id=series.project_id,
            series_id=series.id,
            title=payload.title,
            purpose_markdown=series.purpose_markdown,
            scheduled_start=payload.scheduled_start,
            scheduled_end=payload.scheduled_end,
            host_user_id=series.default_host_user_id,
            recorder_user_id=series.default_recorder_user_id,
            version=1,
            created_by=actor.id,
            updated_by=actor.id,
            participants=self._meeting_participants(participants),
        )
        self.session.add(meeting)
        self.session.commit()
        self.session.refresh(meeting)
        return meeting

    def create_meeting(
        self, project_id: str, payload: MeetingWrite, actor: User
    ) -> Meeting:
        self._require_active(actor)
        self._project(project_id)
        participants = dedupe_participants(payload.participants)
        self._users(
            [payload.host_user_id, payload.recorder_user_id]
            + [value.user_id for value in participants]
        )
        values = payload.model_dump(exclude={"participants"})
        meeting = Meeting(
            project_id=project_id,
            series_id=None,
            **values,
            version=1,
            created_by=actor.id,
            updated_by=actor.id,
            participants=self._meeting_participants(participants),
        )
        self.session.add(meeting)
        self.session.commit()
        self.session.refresh(meeting)
        return meeting

    def _raise_meeting_stale(self, meeting_id: str, expected_version: int, exc: Exception):
        self.session.rollback()
        actual = self.session.scalar(select(Meeting.version).where(Meeting.id == meeting_id))
        if actual is None:
            raise AppError(404, "meeting_not_found", "会议不存在") from exc
        require_version(expected_version, actual)
        raise AppError(409, "version_conflict", "会议已更新，请刷新后重试") from exc

    def update_meeting(
        self, meeting_id: str, payload: MeetingEdit, actor: User
    ) -> Meeting:
        self._require_active(actor)
        meeting = self.get_meeting(meeting_id)
        require_version(payload.expected_version, meeting.version)
        changes = payload.model_dump(
            exclude={"expected_version", "participants"}, exclude_unset=True
        )
        if not changes and payload.participants is None:
            return meeting
        start = changes.get("scheduled_start", meeting.scheduled_start)
        end = changes.get("scheduled_end", meeting.scheduled_end)
        if end <= start:
            raise AppError(422, "invalid_meeting_time", "会议结束时间必须晚于开始时间")
        participants = payload.participants
        if participants is None:
            participants = [
                ParticipantWrite(user_id=row.user_id, participation_role=row.participation_role)
                for row in meeting.participants
            ]
        participants = dedupe_participants(participants)
        self._users(
            [
                changes.get("host_user_id", meeting.host_user_id),
                changes.get("recorder_user_id", meeting.recorder_user_id),
            ]
            + [value.user_id for value in participants]
        )
        for field, value in changes.items():
            setattr(meeting, field, value)
        if payload.participants is not None:
            meeting.participants = self._meeting_participants(participants)
        meeting.updated_by = actor.id
        meeting.version += 1
        try:
            self.session.commit()
        except StaleDataError as exc:
            self._raise_meeting_stale(meeting_id, payload.expected_version, exc)
        self.session.refresh(meeting)
        return meeting

    def serialize_series(self, series: MeetingSeries) -> dict[str, Any]:
        return {
            "id": series.id,
            "project": project_ref(series.project),
            "title": series.title,
            "purpose_markdown": series.purpose_markdown,
            "recurrence_description": series.recurrence_description,
            "default_duration_minutes": series.default_duration_minutes,
            "default_host": user_ref(series.default_host),
            "default_recorder": user_ref(series.default_recorder),
            "status": series.status,
            "version": series.version,
            "participants": [
                {
                    "user": user_ref(row.user),
                    "participation_role": row.participation_role,
                    "position": row.position,
                }
                for row in series.participants
            ],
            "standing_items": [
                {
                    "id": row.id,
                    "title": row.title,
                    "agenda_type": row.agenda_type,
                    "default_owner": user_ref(row.default_owner),
                    "default_duration_minutes": row.default_duration_minutes,
                    "position": row.position,
                }
                for row in series.standing_items
            ],
            "created_by": user_ref(series.creator),
            "updated_by": user_ref(series.updater),
            "created_at": series.created_at,
            "updated_at": series.updated_at,
        }

    def serialize_meeting(self, meeting: Meeting) -> dict[str, Any]:
        return {
            "id": meeting.id,
            "project": project_ref(meeting.project),
            "series": (
                {"id": meeting.series.id, "title": meeting.series.title}
                if meeting.series is not None
                else None
            ),
            "title": meeting.title,
            "purpose_markdown": meeting.purpose_markdown,
            "scheduled_start": meeting.scheduled_start,
            "scheduled_end": meeting.scheduled_end,
            "status": meeting.status,
            "host": user_ref(meeting.host),
            "recorder": user_ref(meeting.recorder),
            "summary_markdown": meeting.summary_markdown,
            "raw_notes_markdown": meeting.raw_notes_markdown,
            "current_snapshot_id": meeting.current_snapshot_id,
            "version": meeting.version,
            "participants": [
                {
                    "user": user_ref(row.user),
                    "participation_role": row.participation_role,
                    "position": row.position,
                }
                for row in meeting.participants
            ],
            "created_by": user_ref(meeting.creator),
            "updated_by": user_ref(meeting.updater),
            "created_at": meeting.created_at,
            "updated_at": meeting.updated_at,
            "started_at": meeting.started_at,
            "completed_at": meeting.completed_at,
        }

    def list_series(self, project_id: str) -> list[dict[str, Any]]:
        self._project(project_id)
        statement = (
            select(MeetingSeries)
            .where(MeetingSeries.project_id == project_id)
            .options(
                joinedload(MeetingSeries.project),
                joinedload(MeetingSeries.default_host),
                joinedload(MeetingSeries.default_recorder),
                joinedload(MeetingSeries.creator),
                joinedload(MeetingSeries.updater),
                selectinload(MeetingSeries.participants).joinedload(SeriesParticipant.user),
                selectinload(MeetingSeries.standing_items).joinedload(StandingAgendaItem.default_owner),
            )
            .order_by(MeetingSeries.updated_at.desc(), MeetingSeries.title, MeetingSeries.id)
        )
        return [self.serialize_series(item) for item in self.session.scalars(statement)]

    def list_meetings(self, project_id: str) -> list[dict[str, Any]]:
        self._project(project_id)
        statement = (
            select(Meeting)
            .where(Meeting.project_id == project_id)
            .options(
                joinedload(Meeting.project),
                joinedload(Meeting.series),
                joinedload(Meeting.host),
                joinedload(Meeting.recorder),
                joinedload(Meeting.creator),
                joinedload(Meeting.updater),
                selectinload(Meeting.participants).joinedload(MeetingParticipant.user),
            )
            .order_by(Meeting.scheduled_start.desc(), Meeting.id)
        )
        return [self.serialize_meeting(item) for item in self.session.scalars(statement)]

    def series_detail(self, series_id: str) -> dict[str, Any]:
        return self.serialize_series(self.get_series(series_id))

    def meeting_detail(self, meeting_id: str) -> dict[str, Any]:
        return self.serialize_meeting(self.get_meeting(meeting_id))

    # Transitional package shape keeps installed plugins/attachments import-safe.
    def package(self, meeting_id: str) -> dict[str, Any]:
        meeting = self.get_meeting(meeting_id)
        result = self.serialize_meeting(meeting)
        result["actions"] = []
        result["updates"] = []
        result["attachments"] = []
        return result

    def plugin_context(self, meeting_id: str, user: User) -> dict[str, Any]:
        result = self.package(meeting_id)
        result["current_user"] = user_ref(user)
        return result
