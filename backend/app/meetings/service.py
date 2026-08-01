from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Iterable

from sqlalchemy import and_, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload, selectinload
from sqlalchemy.orm.exc import StaleDataError

from app.agendas.lifecycle import actual_duration_seconds, start_planned_item
from app.agendas.models import AgendaItem
from app.auth.models import User, UserStatus
from app.collaboration.activity import ActivityRecorder
from app.domain.enums import (
    AgendaStatus,
    MeetingStatus,
    OccurrenceKind,
    RecurrenceFrequency,
    SeriesStatus,
)
from app.domain.versioning import require_version
from app.errors import AppError
from app.attachments.models import Attachment
from app.meetings.models import (
    Meeting,
    MeetingAmendment,
    MeetingParticipant,
    MeetingSeries,
    MeetingSnapshot,
    SeriesParticipant,
    StandingAgendaItem,
)
from app.meetings.recurrence import RecurrenceRule
from app.domain.unit_of_work import UnitOfWork
from app.meetings.lifecycle import MeetingLifecycleCommands
from app.meetings.policies import LifecyclePolicy
from app.meetings.projectors import (
    project_ref as projector_project_ref,
    serialize_amendment as projector_serialize_amendment,
    serialize_attachment as projector_serialize_attachment,
    serialize_snapshot as projector_serialize_snapshot,
    user_ref as projector_user_ref,
)
from app.meetings.queries import MeetingQueries
from app.outcomes.models import ActionItem, DecisionReviewer, OpenQuestion
from app.plugins.events import record_plugin_event
from app.meetings.schemas import (
    AmendmentWrite,
    LifecycleCommand,
    MeetingEdit,
    MeetingSeriesEdit,
    MeetingSeriesWrite,
    MeetingWrite,
    OccurrenceWrite,
    ParticipantWrite,
    StandingAgendaWrite,
    MeetingSnapshotDocument,
)
from app.outcomes.models import Decision
from app.projects.models import Project


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


MAX_RECURRENCE_BACKFILL = timedelta(days=90)


user_ref = projector_user_ref
project_ref = projector_project_ref


def dedupe_participants(values: Iterable[ParticipantWrite]) -> list[ParticipantWrite]:
    """Keep the first occurrence, including its role and original relative order."""
    result: list[ParticipantWrite] = []
    seen: set[str] = set()
    for value in values:
        if value.user_id not in seen:
            seen.add(value.user_id)
            result.append(value)
    return result


def as_utc(value: datetime) -> datetime:
    """Normalize SQLite's naive round-trip as UTC and convert aware values to UTC."""
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def series_relationship_options():
    return (
        joinedload(MeetingSeries.project),
        joinedload(MeetingSeries.default_host),
        joinedload(MeetingSeries.default_recorder),
        joinedload(MeetingSeries.creator),
        joinedload(MeetingSeries.updater),
        selectinload(MeetingSeries.participants).joinedload(SeriesParticipant.user),
        selectinload(MeetingSeries.standing_items).joinedload(
            StandingAgendaItem.default_owner
        ),
    )


def meeting_relationship_options():
    return (
        joinedload(Meeting.project),
        joinedload(Meeting.series),
        joinedload(Meeting.host),
        joinedload(Meeting.recorder),
        joinedload(Meeting.creator),
        joinedload(Meeting.updater),
        selectinload(Meeting.participants).joinedload(MeetingParticipant.user),
        selectinload(Meeting.snapshots).joinedload(MeetingSnapshot.creator),
        joinedload(Meeting.current_snapshot).joinedload(MeetingSnapshot.creator),
        selectinload(Meeting.amendments).joinedload(MeetingAmendment.creator),
        selectinload(Meeting.agenda_items).joinedload(AgendaItem.proposer),
        selectinload(Meeting.agenda_items).joinedload(AgendaItem.presenter),
        selectinload(Meeting.agenda_items).joinedload(AgendaItem.creator),
        selectinload(Meeting.agenda_items).joinedload(AgendaItem.updater),
        selectinload(Meeting.decisions).joinedload(Decision.creator),
        selectinload(Meeting.decisions).joinedload(Decision.decided_by),
        selectinload(Meeting.decisions)
        .selectinload(Decision.reviewers)
        .joinedload(DecisionReviewer.user),
        selectinload(Meeting.actions).joinedload(ActionItem.owner_user),
        selectinload(Meeting.actions).joinedload(ActionItem.creator),
        selectinload(Meeting.open_questions).joinedload(OpenQuestion.owner_user),
        selectinload(Meeting.open_questions).joinedload(OpenQuestion.creator),
    )


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

    def _reload_series(self, series_id: str) -> MeetingSeries:
        series = self.session.scalar(
            select(MeetingSeries)
            .where(MeetingSeries.id == series_id)
            .options(*series_relationship_options())
            .execution_options(populate_existing=True)
        )
        if series is None:
            raise AppError(404, "meeting_series_not_found", "会议系列不存在")
        return series

    def _reload_meeting(self, meeting_id: str) -> Meeting:
        meeting = self.session.scalar(
            select(Meeting)
            .where(Meeting.id == meeting_id)
            .options(*meeting_relationship_options())
            .execution_options(populate_existing=True)
        )
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
    def _meeting_participants(
        values: list[ParticipantWrite],
    ) -> list[MeetingParticipant]:
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
        self.session.flush()
        series_id = series.id
        self.session.commit()
        return self._reload_series(series_id)

    def _raise_series_stale(
        self, series_id: str, expected_version: int, exc: Exception
    ):
        self.session.rollback()
        actual = self.session.scalar(
            select(MeetingSeries.version).where(MeetingSeries.id == series_id)
        )
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
        if (
            not changes
            and payload.participants is None
            and payload.standing_items is None
        ):
            return self._reload_series(series.id)

        participants = payload.participants
        if participants is None:
            participants = [
                ParticipantWrite(
                    user_id=row.user_id, participation_role=row.participation_role
                )
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
            recorder_id=changes.get(
                "default_recorder_user_id", series.default_recorder_user_id
            ),
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
        return self._reload_series(series_id)

    def create_occurrence(
        self, series_id: str, payload: OccurrenceWrite, actor: User
    ) -> Meeting:
        self._require_active(actor)
        series = self.get_series(series_id)
        participants = [
            ParticipantWrite(
                user_id=row.user_id, participation_role=row.participation_role
            )
            for row in series.participants
        ]
        meeting = Meeting(
            project_id=series.project_id,
            series_id=series.id,
            occurrence_kind=OccurrenceKind.manual,
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
        self.session.flush()
        meeting.agenda_items = [
            AgendaItem(
                title=row.title,
                agenda_type=row.agenda_type,
                # Default ownership maps to the occurrence presenter; the
                # proposer remains available for whoever raises it live.
                proposer_user_id=None,
                presenter_user_id=row.default_owner_user_id,
                estimated_minutes=row.default_duration_minutes,
                notes_markdown="",
                position=position,
                version=1,
                created_by=actor.id,
                updated_by=actor.id,
            )
            for position, row in enumerate(series.standing_items)
        ]
        meeting_id = meeting.id
        ActivityRecorder(self.session).record(
            project_id=meeting.project_id,
            meeting_id=meeting.id,
            actor_user_id=actor.id,
            event_type="meeting.created",
            subject_type="meeting",
            subject_id=meeting.id,
            payload={"title": meeting.title},
        )
        self.session.commit()
        return self._reload_meeting(meeting_id)

    @staticmethod
    def _recurrence_rule(series: MeetingSeries) -> RecurrenceRule | None:
        if (
            series.recurrence_frequency is None
            or series.recurrence_local_time is None
            or series.recurrence_timezone is None
            or series.recurrence_anchor_date is None
        ):
            return None
        common = {
            "interval": series.recurrence_interval,
            "local_time": series.recurrence_local_time,
            "timezone_name": series.recurrence_timezone,
            "anchor_date": series.recurrence_anchor_date,
        }
        if series.recurrence_frequency == RecurrenceFrequency.daily:
            return RecurrenceRule.daily(**common)
        if series.recurrence_frequency == RecurrenceFrequency.weekly:
            if series.recurrence_weekday is None:
                return None
            return RecurrenceRule.weekly(
                weekday=series.recurrence_weekday,
                **common,
            )
        if series.recurrence_frequency == RecurrenceFrequency.monthly:
            if series.recurrence_month_day is None:
                return None
            return RecurrenceRule.monthly(
                month_day=series.recurrence_month_day,
                **common,
            )
        if (
            series.recurrence_month is None
            or series.recurrence_month_day is None
        ):
            return None
        return RecurrenceRule.yearly(
            month=series.recurrence_month,
            month_day=series.recurrence_month_day,
            **common,
        )

    def _create_series_occurrence(
        self,
        series: MeetingSeries,
        *,
        slot_at: datetime,
        created_by: str,
    ) -> Meeting:
        participants = [
            ParticipantWrite(
                user_id=row.user_id, participation_role=row.participation_role
            )
            for row in series.participants
        ]
        meeting = Meeting(
            project_id=series.project_id,
            series_id=series.id,
            occurrence_kind=OccurrenceKind.scheduled,
            series_slot_at=slot_at,
            title=series.title,
            purpose_markdown=series.purpose_markdown,
            scheduled_start=slot_at,
            scheduled_end=slot_at + timedelta(minutes=series.default_duration_minutes),
            host_user_id=series.default_host_user_id,
            recorder_user_id=series.default_recorder_user_id,
            version=1,
            created_by=created_by,
            updated_by=created_by,
            participants=self._meeting_participants(participants),
        )
        meeting.agenda_items = [
            AgendaItem(
                title=row.title,
                agenda_type=row.agenda_type,
                proposer_user_id=None,
                presenter_user_id=row.default_owner_user_id,
                estimated_minutes=row.default_duration_minutes,
                notes_markdown="",
                position=position,
                version=1,
                created_by=created_by,
                updated_by=created_by,
            )
            for position, row in enumerate(series.standing_items)
        ]
        self.session.add(meeting)
        return meeting

    def _materialize_series(
        self, series: MeetingSeries, *, now: datetime
    ) -> list[str]:
        rule = self._recurrence_rule(series)
        if rule is None:
            return []
        slots = rule.slots_through(
            now,
            earliest=as_utc(now) - MAX_RECURRENCE_BACKFILL,
        )
        if not slots:
            return []
        existing_slots = {
            as_utc(slot_at)
            for slot_at in self.session.scalars(
                select(Meeting.series_slot_at).where(
                    Meeting.series_id == series.id,
                    Meeting.series_slot_at.in_(slots),
                )
            )
            if slot_at is not None
        }
        created: list[str] = []
        for slot_at in slots:
            if as_utc(slot_at) in existing_slots:
                continue
            try:
                with self.session.begin_nested():
                    meeting = self._create_series_occurrence(
                        series,
                        slot_at=slot_at,
                        created_by=series.updated_by,
                    )
                    self.session.flush()
                    created.append(meeting.id)
            except IntegrityError:
                # A second application worker can win the unique slot race.
                # The committed row is then the authoritative occurrence.
                continue
        return created

    def materialize_due_occurrences(
        self, *, now: datetime, project_id: str | None = None
    ) -> list[Meeting]:
        if now.tzinfo is None or now.utcoffset() is None:
            now = now.replace(tzinfo=timezone.utc)
        statement = select(MeetingSeries).where(
            MeetingSeries.status == SeriesStatus.active,
            MeetingSeries.recurrence_frequency.is_not(None),
        )
        if project_id is not None:
            statement = statement.where(MeetingSeries.project_id == project_id)
        series = list(self.session.scalars(statement.options(*series_relationship_options())))
        created_ids = [
            meeting_id
            for item in series
            for meeting_id in self._materialize_series(item, now=now)
        ]
        if not created_ids:
            return []
        self.session.commit()
        return [self._reload_meeting(meeting_id) for meeting_id in created_ids]

    def reconcile_series(
        self, series_id: str, *, now: datetime, commit: bool = True
    ) -> list[Meeting]:
        series = self._reload_series(series_id)
        if series.status != SeriesStatus.active:
            return []
        created_ids = self._materialize_series(series, now=now)
        if not created_ids:
            return []
        if commit:
            self.session.commit()
        return [self._reload_meeting(meeting_id) for meeting_id in created_ids]

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
        self.session.flush()
        meeting_id = meeting.id
        ActivityRecorder(self.session).record(
            project_id=meeting.project_id,
            meeting_id=meeting.id,
            actor_user_id=actor.id,
            event_type="meeting.created",
            subject_type="meeting",
            subject_id=meeting.id,
            payload={"title": meeting.title},
        )
        self.session.commit()
        return self._reload_meeting(meeting_id)

    def _raise_meeting_stale(
        self, meeting_id: str, expected_version: int, exc: Exception
    ):
        self.session.rollback()
        actual = self.session.scalar(
            select(Meeting.version).where(Meeting.id == meeting_id)
        )
        if actual is None:
            raise AppError(404, "meeting_not_found", "会议不存在") from exc
        require_version(expected_version, actual)
        raise AppError(409, "version_conflict", "会议已更新，请刷新后重试") from exc

    def update_meeting(
        self, meeting_id: str, payload: MeetingEdit, actor: User
    ) -> Meeting:
        self._require_active(actor)
        meeting = self.get_meeting(meeting_id)
        if meeting.status in {MeetingStatus.completed, MeetingStatus.canceled}:
            raise AppError(409, "meeting_locked", "已结束的会议不可直接修改")
        require_version(payload.expected_version, meeting.version)
        changes = payload.model_dump(
            exclude={"expected_version", "participants"}, exclude_unset=True
        )
        if not changes and payload.participants is None:
            return self._reload_meeting(meeting.id)
        start = as_utc(changes.get("scheduled_start", meeting.scheduled_start))
        end = as_utc(changes.get("scheduled_end", meeting.scheduled_end))
        if end <= start:
            raise AppError(422, "invalid_meeting_time", "会议结束时间必须晚于开始时间")
        participants = payload.participants
        if participants is None:
            participants = [
                ParticipantWrite(
                    user_id=row.user_id, participation_role=row.participation_role
                )
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
        ActivityRecorder(self.session).record(
            project_id=meeting.project_id,
            meeting_id=meeting.id,
            actor_user_id=actor.id,
            event_type="meeting.updated",
            subject_type="meeting",
            subject_id=meeting.id,
            payload={"title": meeting.title},
        )
        try:
            self.session.commit()
        except StaleDataError as exc:
            self._raise_meeting_stale(meeting_id, payload.expected_version, exc)
        return self._reload_meeting(meeting_id)

    @staticmethod
    def _invalid_transition(meeting: Meeting, target: MeetingStatus) -> None:
        raise AppError(
            409,
            "invalid_state_transition",
            "会议状态不可执行此操作",
            details={"from": meeting.status.value, "to": target.value},
        )

    def _record_meeting(self, meeting: Meeting, actor: User, event_type: str) -> None:
        ActivityRecorder(self.session).record(
            project_id=meeting.project_id,
            meeting_id=meeting.id,
            actor_user_id=actor.id,
            event_type=event_type,
            subject_type="meeting",
            subject_id=meeting.id,
            payload={"title": meeting.title},
        )

    def _commit_meeting_command(
        self, meeting: Meeting, expected_version: int, *, commit: bool = True
    ) -> Meeting:
        meeting_id = meeting.id
        meeting.version += 1
        if not commit:
            return meeting
        try:
            self.session.commit()
        except (StaleDataError, IntegrityError) as exc:
            self._raise_meeting_stale(meeting_id, expected_version, exc)
        return self._reload_meeting(meeting_id)

    def mark_ready(
        self, meeting_id: str, payload: LifecycleCommand, actor: User
    ) -> Meeting:
        self._require_active(actor)
        meeting = self.get_meeting(meeting_id)
        require_version(payload.expected_version, meeting.version)
        if meeting.status != MeetingStatus.draft:
            self._invalid_transition(meeting, MeetingStatus.ready)
        meeting.status = MeetingStatus.ready
        meeting.updated_by = actor.id
        self._record_meeting(meeting, actor, "meeting.ready")
        return self._commit_meeting_command(meeting, payload.expected_version)

    def mark_draft(
        self, meeting_id: str, payload: LifecycleCommand, actor: User
    ) -> Meeting:
        self._require_active(actor)
        meeting = self.get_meeting(meeting_id)
        require_version(payload.expected_version, meeting.version)
        if meeting.status != MeetingStatus.ready:
            self._invalid_transition(meeting, MeetingStatus.draft)
        meeting.status = MeetingStatus.draft
        meeting.updated_by = actor.id
        self._record_meeting(meeting, actor, "meeting.returned_to_draft")
        return self._commit_meeting_command(meeting, payload.expected_version)

    def start(self, meeting_id: str, payload: LifecycleCommand, actor: User) -> Meeting:
        return MeetingLifecycleCommands(self, UnitOfWork(self.session)).start(
            meeting_id, payload, actor
        )

    def _start_impl(
        self, meeting_id: str, payload: LifecycleCommand, actor: User, *, commit: bool = True
    ) -> Meeting:
        self._require_active(actor)
        meeting = self.get_meeting(meeting_id)
        require_version(payload.expected_version, meeting.version)
        LifecyclePolicy.require(
            meeting.status,
            MeetingStatus.in_progress,
            LifecyclePolicy.can_start(meeting.status),
        )
        if (
            meeting.occurrence_kind == OccurrenceKind.scheduled
            and meeting.series_id is not None
        ):
            self.reconcile_series(meeting.series_id, now=utcnow(), commit=False)
            meeting = self.get_meeting(meeting_id)
        require_version(payload.expected_version, meeting.version)
        now = utcnow()
        if (
            meeting.occurrence_kind == OccurrenceKind.scheduled
            and meeting.series_id is not None
            and meeting.series_slot_at is not None
        ):
            previous_ids = list(self.session.scalars(
                select(Meeting.id)
                .where(
                    Meeting.series_id == meeting.series_id,
                    Meeting.occurrence_kind == OccurrenceKind.scheduled,
                    Meeting.series_slot_at < meeting.series_slot_at,
                    Meeting.status.in_(
                        [
                            MeetingStatus.draft,
                            MeetingStatus.ready,
                            MeetingStatus.in_progress,
                        ]
                    ),
                )
                .order_by(Meeting.series_slot_at)
            ))
            for previous_id in previous_ids:
                previous = self._meeting_for_snapshot(previous_id)
                self._finish_in_session(previous, actor=actor, now=now)
        meeting.status = MeetingStatus.in_progress
        meeting.started_at = meeting.started_at or now
        meeting.updated_by = actor.id
        first_planned = next(
            (
                item
                for item in sorted(
                    meeting.agenda_items, key=lambda row: (row.position, row.id)
                )
                if item.status == AgendaStatus.planned
            ),
            None,
        )
        if first_planned is not None:
            start_planned_item(first_planned, actor_id=actor.id, at=now)
            ActivityRecorder(self.session).record(
                project_id=meeting.project_id,
                meeting_id=meeting.id,
                actor_user_id=actor.id,
                event_type="agenda.started",
                subject_type="agenda_item",
                subject_id=first_planned.id,
                payload={"title": first_planned.title},
            )
        self._record_meeting(meeting, actor, "meeting.started")
        return self._commit_meeting_command(
            meeting, payload.expected_version, commit=commit
        )

    def cancel(
        self, meeting_id: str, payload: LifecycleCommand, actor: User
    ) -> Meeting:
        self._require_active(actor)
        meeting = self.get_meeting(meeting_id)
        require_version(payload.expected_version, meeting.version)
        if meeting.status not in {
            MeetingStatus.draft,
            MeetingStatus.ready,
            MeetingStatus.in_progress,
        }:
            self._invalid_transition(meeting, MeetingStatus.canceled)
        meeting.status = MeetingStatus.canceled
        meeting.completed_at = None
        meeting.updated_by = actor.id
        self._record_meeting(meeting, actor, "meeting.canceled")
        return self._commit_meeting_command(meeting, payload.expected_version)

    def reopen(
        self, meeting_id: str, payload: LifecycleCommand, actor: User
    ) -> Meeting:
        self._require_active(actor)
        meeting = self.get_meeting(meeting_id)
        require_version(payload.expected_version, meeting.version)
        if meeting.status != MeetingStatus.completed:
            self._invalid_transition(meeting, MeetingStatus.in_progress)
        meeting.status = MeetingStatus.in_progress
        meeting.started_at = meeting.started_at or utcnow()
        meeting.completed_at = None
        meeting.updated_by = actor.id
        self._record_meeting(meeting, actor, "meeting.reopened")
        return self._commit_meeting_command(meeting, payload.expected_version)

    def _meeting_for_snapshot(self, meeting_id: str) -> Meeting:
        meeting = self.session.scalar(
            select(Meeting)
            .where(Meeting.id == meeting_id)
            .options(
                selectinload(Meeting.participants),
                selectinload(Meeting.amendments),
                selectinload(Meeting.agenda_items)
                .selectinload(AgendaItem.decisions)
                .selectinload(Decision.reviewers),
                selectinload(Meeting.agenda_items).selectinload(AgendaItem.actions),
                selectinload(Meeting.agenda_items).selectinload(
                    AgendaItem.open_questions
                ),
                selectinload(Meeting.decisions).selectinload(Decision.reviewers),
                selectinload(Meeting.actions),
                selectinload(Meeting.open_questions),
            )
        )
        if meeting is None:
            raise AppError(404, "meeting_not_found", "会议不存在")
        return meeting

    @staticmethod
    def _snapshot_document(meeting: Meeting) -> dict[str, Any]:
        def columns(item, names):
            return {
                name: (
                    as_utc(value)
                    if isinstance(value := getattr(item, name), datetime)
                    else value
                )
                for name in names
            }

        def decision_document(decision):
            result = columns(
                decision,
                (
                    "id",
                    "project_id",
                    "meeting_id",
                    "agenda_item_id",
                    "source_agenda_item_id",
                    "source_tag_key",
                    "title",
                    "decision_markdown",
                    "rationale_markdown",
                    "status",
                    "decided_by_user_id",
                    "supersedes_decision_id",
                    "version",
                    "created_by",
                    "created_at",
                    "updated_at",
                ),
            )
            result["is_derived"] = decision.source_agenda_item_id is not None
            result["reviewers"] = [
                columns(row, ("user_id", "status", "responded_at", "comment"))
                for row in sorted(decision.reviewers, key=lambda row: row.user_id)
            ]
            return result

        def action_document(row):
            result = columns(
                row,
                (
                    "id",
                    "project_id",
                    "meeting_id",
                    "agenda_item_id",
                    "source_agenda_item_id",
                    "source_tag_key",
                    "content",
                    "owner_user_id",
                    "due_date",
                    "priority",
                    "status",
                    "version",
                    "created_by",
                    "created_at",
                    "updated_at",
                    "completed_at",
                ),
            )
            result["is_derived"] = row.source_agenda_item_id is not None
            return result

        def question_document(row):
            result = columns(
                row,
                (
                    "id",
                    "project_id",
                    "meeting_id",
                    "agenda_item_id",
                    "source_agenda_item_id",
                    "source_tag_key",
                    "question_markdown",
                    "owner_user_id",
                    "status",
                    "scheduled_meeting_id",
                    "resolved_by_decision_id",
                    "converted_from_agenda_item_id",
                    "version",
                    "created_by",
                    "created_at",
                    "updated_at",
                ),
            )
            result["is_derived"] = row.source_agenda_item_id is not None
            return result

        agenda_documents = []
        for item in sorted(
            meeting.agenda_items, key=lambda row: (row.position, row.id)
        ):
            item_data = columns(
                item,
                (
                    "id",
                    "meeting_id",
                    "title",
                    "agenda_type",
                    "proposer_user_id",
                    "presenter_user_id",
                    "estimated_minutes",
                    "actual_duration_seconds",
                    "notes_markdown",
                    "status",
                    "position",
                    "carry_from_open_question_id",
                    "copied_from_agenda_item_id",
                    "version",
                    "created_by",
                    "updated_by",
                    "created_at",
                    "updated_at",
                    "started_at",
                    "completed_at",
                ),
            )
            item_data["decisions"] = []
            for decision in sorted(item.decisions, key=lambda row: row.id):
                item_data["decisions"].append(decision_document(decision))
            item_data["actions"] = [
                action_document(row)
                for row in sorted(item.actions, key=lambda row: row.id)
            ]
            item_data["open_questions"] = [
                question_document(row)
                for row in sorted(item.open_questions, key=lambda row: row.id)
            ]
            agenda_documents.append(item_data)
        meeting_data = columns(
            meeting,
            (
                "id",
                "project_id",
                "series_id",
                "title",
                "purpose_markdown",
                "scheduled_start",
                "scheduled_end",
                "host_user_id",
                "recorder_user_id",
                "summary_markdown",
                "raw_notes_markdown",
                "created_by",
                "updated_by",
                "created_at",
                "updated_at",
                "started_at",
                "completed_at",
            ),
        )
        meeting_data["status_before_completion"] = meeting.status
        meeting_data["version_before_completion"] = meeting.version
        meeting_data["participants"] = [
            columns(row, ("user_id", "participation_role", "position"))
            for row in sorted(
                meeting.participants, key=lambda row: (row.position, row.user_id)
            )
        ]
        amendments = [
            columns(
                row, ("id", "reason", "content_markdown", "created_by", "created_at")
            )
            for row in sorted(
                meeting.amendments, key=lambda row: (row.created_at, row.id)
            )
        ]
        document = MeetingSnapshotDocument(
            meeting=meeting_data,
            agenda_items=agenda_documents,
            meeting_decisions=[
                decision_document(row)
                for row in sorted(meeting.decisions, key=lambda row: row.id)
                if row.agenda_item_id is None
            ],
            meeting_actions=[
                action_document(row)
                for row in sorted(meeting.actions, key=lambda row: row.id)
                if row.agenda_item_id is None
            ],
            meeting_open_questions=[
                question_document(row)
                for row in sorted(meeting.open_questions, key=lambda row: row.id)
                if row.agenda_item_id is None
            ],
            amendments=amendments,
        )
        return document.model_dump(mode="json")

    @staticmethod
    def _validate_outcome_source_chain(meeting: Meeting) -> None:
        agenda_ids = {item.id for item in meeting.agenda_items}
        candidates = (
            [("decision", row) for row in meeting.decisions]
            + [("action", row) for row in meeting.actions]
            + [("open_question", row) for row in meeting.open_questions]
        )
        for agenda in meeting.agenda_items:
            candidates.extend(("decision", row) for row in agenda.decisions)
            candidates.extend(("action", row) for row in agenda.actions)
            candidates.extend(("open_question", row) for row in agenda.open_questions)

        invalid = []
        seen = set()
        for outcome_type, outcome in candidates:
            key = (outcome_type, outcome.id)
            if key in seen:
                continue
            seen.add(key)
            violations = []
            if outcome.project_id != meeting.project_id:
                violations.append("project_id")
            if outcome.meeting_id != meeting.id:
                violations.append("meeting_id")
            if (
                outcome.agenda_item_id is not None
                and outcome.agenda_item_id not in agenda_ids
            ):
                violations.append("agenda_item_id")
            if violations:
                invalid.append(
                    {
                        "outcome_type": outcome_type,
                        "outcome_id": outcome.id,
                        "project_id": outcome.project_id,
                        "meeting_id": outcome.meeting_id,
                        "agenda_item_id": outcome.agenda_item_id,
                        "violations": violations,
                    }
                )

        if invalid:
            invalid.sort(key=lambda row: (row["outcome_type"], row["outcome_id"]))
            raise AppError(
                409,
                "invalid_outcome_source_chain",
                "会议成果来源链不完整",
                details={"outcomes": invalid},
            )

    def finish(
        self, meeting_id: str, payload: LifecycleCommand, actor: User
    ) -> Meeting:
        return MeetingLifecycleCommands(self, UnitOfWork(self.session)).finish(
            meeting_id, payload, actor
        )

    def _finish_impl(
        self, meeting_id: str, payload: LifecycleCommand, actor: User, *, commit: bool = True
    ) -> Meeting:
        self._require_active(actor)
        meeting = self._meeting_for_snapshot(meeting_id)
        require_version(payload.expected_version, meeting.version)
        LifecyclePolicy.require(
            meeting.status,
            MeetingStatus.completed,
            LifecyclePolicy.can_finish(meeting.status),
        )
        self._finish_in_session(meeting, actor=actor, now=utcnow())
        meeting_id = meeting.id
        if not commit:
            return meeting
        try:
            self.session.commit()
        except (StaleDataError, IntegrityError) as exc:
            self._raise_meeting_stale(meeting_id, payload.expected_version, exc)
        return self._reload_meeting(meeting_id)

    def _finish_in_session(
        self, meeting: Meeting, *, actor: User, now: datetime
    ) -> None:
        self._validate_outcome_source_chain(meeting)
        for item in meeting.agenda_items:
            if item.status not in {AgendaStatus.planned, AgendaStatus.in_progress}:
                continue
            item.status = AgendaStatus.skipped
            item.completed_at = now
            item.actual_duration_seconds = actual_duration_seconds(item, now)
            item.updated_by = actor.id
            item.version += 1
        completion_number = (
            self.session.scalar(
                select(func.max(MeetingSnapshot.completion_number)).where(
                    MeetingSnapshot.meeting_id == meeting.id
                )
            )
            or 0
        ) + 1
        meeting.status = MeetingStatus.completed
        meeting.completed_at = now
        meeting.updated_by = actor.id
        snapshot = MeetingSnapshot(
            meeting_id=meeting.id,
            completion_number=completion_number,
            snapshot_json=self._snapshot_document(meeting),
            created_by=actor.id,
        )
        self.session.add(snapshot)
        meeting.current_snapshot = snapshot
        meeting.version += 1
        self.session.flush()
        record_plugin_event(
            self.session,
            event_type="meeting.completed",
            target_type="meeting",
            target_id=meeting.id,
            event_id=f"meeting.completed:meeting:{meeting.id}:{completion_number}",
            payload={
                "meeting_id": meeting.id,
                "snapshot_id": snapshot.id,
                "version": meeting.version,
            },
        )
        self._record_meeting(meeting, actor, "meeting.finished")

    def list_snapshots(
        self, meeting_id: str, *, limit: int = 50, offset: int = 0
    ) -> list[MeetingSnapshot]:
        self.get_meeting(meeting_id)
        return list(
            self.session.scalars(
                select(MeetingSnapshot)
                .where(MeetingSnapshot.meeting_id == meeting_id)
                .options(joinedload(MeetingSnapshot.creator))
                .order_by(MeetingSnapshot.completion_number, MeetingSnapshot.id)
                .limit(min(max(limit, 1), 200))
                .offset(max(offset, 0))
            )
        )

    def add_amendment(
        self, meeting_id: str, payload: AmendmentWrite, actor: User
    ) -> MeetingAmendment:
        self._require_active(actor)
        meeting = self.get_meeting(meeting_id)
        require_version(payload.expected_version, meeting.version)
        if meeting.status != MeetingStatus.completed:
            raise AppError(409, "meeting_not_completed", "只有已完成会议可添加更正")
        amendment = MeetingAmendment(
            meeting_id=meeting.id,
            reason=payload.reason,
            content_markdown=payload.content_markdown,
            created_by=actor.id,
        )
        self.session.add(amendment)
        self.session.flush()
        meeting.updated_by = actor.id
        ActivityRecorder(self.session).record(
            project_id=meeting.project_id,
            meeting_id=meeting.id,
            actor_user_id=actor.id,
            event_type="meeting.amended",
            subject_type="meeting_amendment",
            subject_id=amendment.id,
            payload={"meeting_id": meeting.id},
        )
        self._commit_meeting_command(meeting, payload.expected_version)
        self.session.refresh(amendment)
        return amendment

    @staticmethod
    def serialize_snapshot(item: MeetingSnapshot) -> dict[str, Any]:
        return projector_serialize_snapshot(item)

    @staticmethod
    def serialize_amendment(item: MeetingAmendment) -> dict[str, Any]:
        return projector_serialize_amendment(item)

    def serialize_series(self, series: MeetingSeries) -> dict[str, Any]:
        return {
            "id": series.id,
            "project": project_ref(series.project),
            "title": series.title,
            "purpose_markdown": series.purpose_markdown,
            "recurrence_description": series.recurrence_description,
            "recurrence": {
                "frequency": (
                    series.recurrence_frequency.value
                    if series.recurrence_frequency is not None
                    else None
                ),
                "interval": series.recurrence_interval,
                "weekday": series.recurrence_weekday,
                "month_day": series.recurrence_month_day,
                "month": series.recurrence_month,
                "local_time": (
                    series.recurrence_local_time.isoformat()
                    if series.recurrence_local_time is not None
                    else None
                ),
                "timezone": series.recurrence_timezone,
                "anchor_date": (
                    series.recurrence_anchor_date.isoformat()
                    if series.recurrence_anchor_date is not None
                    else None
                ),
            },
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
        from app.outcomes.service import OutcomeService

        def decision_detail(item: Decision) -> dict[str, Any]:
            result = OutcomeService.serialize(item)
            result["created_by_user_id"] = item.created_by
            result["created_by"] = user_ref(item.creator)
            result["decided_by"] = user_ref(item.decided_by)
            result["reviewers"] = [
                {
                    "user_id": row.user_id,
                    "user": user_ref(row.user),
                    "status": row.status,
                    "responded_at": row.responded_at,
                    "comment": row.comment,
                }
                for row in item.reviewers
            ]
            return result

        def action_detail(item: ActionItem) -> dict[str, Any]:
            result = OutcomeService.serialize(item)
            result["created_by_user_id"] = item.created_by
            result["created_by"] = user_ref(item.creator)
            result["owner"] = user_ref(item.owner_user)
            return result

        def question_detail(item: OpenQuestion) -> dict[str, Any]:
            result = OutcomeService.serialize(item)
            result["created_by_user_id"] = item.created_by
            result["created_by"] = user_ref(item.creator)
            result["owner"] = user_ref(item.owner_user)
            return result

        def group_by_agenda(items):
            grouped = {}
            for item in sorted(items, key=lambda value: value.id):
                grouped.setdefault(item.agenda_item_id, []).append(item)
            return grouped

        decisions_by_agenda = group_by_agenda(meeting.decisions)
        actions_by_agenda = group_by_agenda(meeting.actions)
        questions_by_agenda = group_by_agenda(meeting.open_questions)

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
            "occurrence_kind": meeting.occurrence_kind.value,
            "series_slot_at": (
                as_utc(meeting.series_slot_at)
                if meeting.series_slot_at is not None
                else None
            ),
            "scheduled_start": as_utc(meeting.scheduled_start),
            "scheduled_end": as_utc(meeting.scheduled_end),
            "status": meeting.status,
            "host": user_ref(meeting.host),
            "recorder": user_ref(meeting.recorder),
            "summary_markdown": meeting.summary_markdown,
            "raw_notes_markdown": meeting.raw_notes_markdown,
            "current_snapshot_id": meeting.current_snapshot_id,
            "current_snapshot": (
                {
                    "id": meeting.current_snapshot.id,
                    "completion_number": meeting.current_snapshot.completion_number,
                    "snapshot_json": meeting.current_snapshot.snapshot_json,
                    "created_by_user_id": meeting.current_snapshot.created_by,
                    "created_by": user_ref(meeting.current_snapshot.creator),
                    "created_at": meeting.current_snapshot.created_at,
                }
                if meeting.current_snapshot is not None
                else None
            ),
            "snapshots": [
                {
                    "id": row.id,
                    "completion_number": row.completion_number,
                    "created_by_user_id": row.created_by,
                    "created_by": user_ref(row.creator),
                    "created_at": row.created_at,
                }
                for row in meeting.snapshots
            ],
            "amendments": [self.serialize_amendment(row) for row in meeting.amendments],
            "version": meeting.version,
            "participants": [
                {
                    "user": user_ref(row.user),
                    "participation_role": row.participation_role,
                    "position": row.position,
                }
                for row in meeting.participants
            ],
            "agenda_items": [
                {
                    "id": row.id,
                    "meeting_id": row.meeting_id,
                    "title": row.title,
                    "agenda_type": row.agenda_type,
                    "proposer": user_ref(row.proposer),
                    "presenter": user_ref(row.presenter),
                    "estimated_minutes": row.estimated_minutes,
                    "actual_duration_seconds": row.actual_duration_seconds,
                    "notes_markdown": row.notes_markdown,
                    "status": row.status,
                    "position": row.position,
                    "carry_from_open_question_id": row.carry_from_open_question_id,
                    "version": row.version,
                    "created_by": user_ref(row.creator),
                    "updated_by": user_ref(row.updater),
                    "created_at": row.created_at,
                    "updated_at": row.updated_at,
                    "started_at": row.started_at,
                    "completed_at": row.completed_at,
                    "decisions": [
                        decision_detail(item)
                        for item in decisions_by_agenda.get(row.id, [])
                    ],
                    "actions": [
                        action_detail(item)
                        for item in actions_by_agenda.get(row.id, [])
                    ],
                    "open_questions": [
                        question_detail(item)
                        for item in questions_by_agenda.get(row.id, [])
                    ],
                }
                for row in meeting.agenda_items
            ],
            "meeting_decisions": [
                decision_detail(item) for item in decisions_by_agenda.get(None, [])
            ],
            "meeting_actions": [
                action_detail(item) for item in actions_by_agenda.get(None, [])
            ],
            "meeting_open_questions": [
                question_detail(item) for item in questions_by_agenda.get(None, [])
            ],
            "created_by": user_ref(meeting.creator),
            "updated_by": user_ref(meeting.updater),
            "created_at": meeting.created_at,
            "updated_at": meeting.updated_at,
            "started_at": meeting.started_at,
            "completed_at": meeting.completed_at,
        }

    def list_series(self, project_id: str) -> list[dict[str, Any]]:
        return MeetingQueries(self).list_series(project_id)

    def _list_series_impl(self, project_id: str) -> list[dict[str, Any]]:
        self._project(project_id)
        self.materialize_due_occurrences(now=utcnow(), project_id=project_id)
        statement = (
            select(MeetingSeries)
            .where(MeetingSeries.project_id == project_id)
            .options(
                *series_relationship_options(),
            )
            .order_by(
                MeetingSeries.updated_at.desc(), MeetingSeries.title, MeetingSeries.id
            )
        )
        return [self.serialize_series(item) for item in self.session.scalars(statement)]

    def list_meetings(self, project_id: str) -> list[dict[str, Any]]:
        return MeetingQueries(self).list_meetings(project_id)

    def _list_meetings_impl(self, project_id: str) -> list[dict[str, Any]]:
        self._project(project_id)
        self.materialize_due_occurrences(now=utcnow(), project_id=project_id)
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
        statement = (
            select(Meeting, agenda_count, snapshot_count, amendment_count)
            .where(Meeting.project_id == project_id)
            .options(
                joinedload(Meeting.project),
                joinedload(Meeting.series),
                joinedload(Meeting.host),
                joinedload(Meeting.recorder),
            )
            .order_by(Meeting.scheduled_start.desc(), Meeting.id)
        )
        return [
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
                "series_slot_at": (
                    as_utc(meeting.series_slot_at)
                    if meeting.series_slot_at is not None
                    else None
                ),
                "scheduled_start": as_utc(meeting.scheduled_start),
                "scheduled_end": as_utc(meeting.scheduled_end),
                "status": meeting.status,
                "host": user_ref(meeting.host),
                "recorder": user_ref(meeting.recorder),
                "current_snapshot_id": meeting.current_snapshot_id,
                "version": meeting.version,
                "started_at": meeting.started_at,
                "completed_at": meeting.completed_at,
                "agenda_count": agenda_total,
                "snapshot_count": snapshot_total,
                "amendment_count": amendment_total,
            }
            for meeting, agenda_total, snapshot_total, amendment_total in self.session.execute(
                statement
            )
        ]

    def series_detail(self, series_id: str) -> dict[str, Any]:
        return MeetingQueries(self).series_detail(series_id)

    def _series_detail_impl(self, series_id: str) -> dict[str, Any]:
        self.reconcile_series(series_id, now=utcnow())
        series = self.session.scalar(
            select(MeetingSeries)
            .where(MeetingSeries.id == series_id)
            .options(*series_relationship_options())
        )
        if series is None:
            raise AppError(404, "meeting_series_not_found", "会议系列不存在")
        return self.serialize_series(series)

    def meeting_detail(self, meeting_id: str) -> dict[str, Any]:
        return MeetingQueries(self).meeting_detail(meeting_id)

    def _meeting_detail_impl(self, meeting_id: str) -> dict[str, Any]:
        meeting = self.session.scalar(
            select(Meeting)
            .where(Meeting.id == meeting_id)
            .options(*meeting_relationship_options())
        )
        if meeting is None:
            raise AppError(404, "meeting_not_found", "会议不存在")
        result = self.serialize_meeting(meeting)
        target_ids = [meeting.id] + [row.id for row in meeting.agenda_items]
        attachments = list(
            self.session.scalars(
                select(Attachment)
                .where(
                    or_(
                        and_(
                            Attachment.target_type == "meeting",
                            Attachment.target_id == meeting.id,
                        ),
                        and_(
                            Attachment.target_type == "agenda_item",
                            Attachment.target_id.in_(target_ids[1:]),
                        ),
                    )
                )
                .options(joinedload(Attachment.creator))
                .order_by(Attachment.created_at.desc(), Attachment.id.desc())
            )
        )
        grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
        for item in attachments:
            grouped.setdefault((item.target_type, item.target_id), []).append(
                self.serialize_attachment(item)
            )
        result["attachments"] = grouped.get(("meeting", meeting.id), [])
        for agenda in result["agenda_items"]:
            agenda["attachments"] = grouped.get(("agenda_item", agenda["id"]), [])
        return result

    def _actor(self, user_id: str) -> dict[str, str]:
        user = self.session.get(User, user_id)
        if user is None:
            raise AppError(500, "actor_not_found", "记录创建者不存在")
        return user_ref(user)

    def serialize_attachment(self, item: Attachment) -> dict[str, Any]:
        return projector_serialize_attachment(item)

    def serialize_action(self, item: ActionItem) -> dict[str, Any]:
        meeting = self.get_meeting(item.meeting_id)
        return {
            "id": item.id,
            "meeting_id": item.meeting_id,
            "meeting_title": meeting.title,
            "content": item.content,
            "owner": (
                item.owner_user.display_name or item.owner_user.username
                if item.owner_user is not None
                else ""
            ),
            "due_date": item.due_date,
            "status": item.status.value,
            "created_by": self._actor(item.created_by),
            "created_at": item.created_at,
            "updated_at": item.updated_at,
        }

    def package(self, meeting_id: str) -> dict[str, Any]:
        return MeetingQueries(self).package(meeting_id)

    def _package_impl(self, meeting_id: str) -> dict[str, Any]:
        result = self.meeting_detail(meeting_id)
        actions = self.session.scalars(
            select(ActionItem)
            .where(ActionItem.meeting_id == meeting_id)
            .options(joinedload(ActionItem.owner_user))
            .order_by(ActionItem.created_at, ActionItem.id)
        )
        attachments = self.session.scalars(
            select(Attachment)
            .where(
                Attachment.target_type == "meeting", Attachment.target_id == meeting_id
            )
            .options(joinedload(Attachment.creator))
            .order_by(Attachment.created_at.desc(), Attachment.id.desc())
        )
        result["actions"] = [self.serialize_action(item) for item in actions]
        result["updates"] = list(result["amendments"])
        result["attachments"] = [
            self.serialize_attachment(item) for item in attachments
        ]
        return result

    def plugin_context(self, meeting_id: str, user: User) -> dict[str, Any]:
        return MeetingQueries(self).plugin_context(meeting_id, user)

    def _plugin_context_impl(self, meeting_id: str, user: User) -> dict[str, Any]:
        package = self.package(meeting_id)
        # api_version=1 plugins consume the former flat meeting contract. New
        # standalone meetings have no free-form type, so expose a deterministic
        # source kind while keeping the 1.0 API serialization untouched.
        return {
            **package,
            "agenda_outcome_tags": ["@决策:", "@行动:", "@开放问题:"],
            "project": package["project"]["name"],
            "meeting_type": "series" if package["series"] else "standalone",
            "meeting_date": package["scheduled_start"],
            "participants": [
                item["user"]["display_name"] or item["user"]["username"]
                for item in package["participants"]
            ],
            "conclusions_markdown": package["summary_markdown"],
            "current_user": user_ref(user),
        }
