from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable

from sqlalchemy import and_, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload, selectinload
from sqlalchemy.orm.exc import StaleDataError

from app.agendas.models import AgendaItem
from app.auth.models import User, UserStatus
from app.domain.enums import AgendaStatus, MeetingStatus
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
from app.outcomes.models import ActionItem, DecisionReviewer, OpenQuestion
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
        selectinload(Meeting.agenda_items)
        .selectinload(AgendaItem.decisions)
        .joinedload(Decision.creator),
        selectinload(Meeting.agenda_items)
        .selectinload(AgendaItem.decisions)
        .joinedload(Decision.decided_by),
        selectinload(Meeting.agenda_items)
        .selectinload(AgendaItem.decisions)
        .selectinload(Decision.reviewers)
        .joinedload(DecisionReviewer.user),
        selectinload(Meeting.agenda_items)
        .selectinload(AgendaItem.actions)
        .joinedload(ActionItem.owner_user),
        selectinload(Meeting.agenda_items)
        .selectinload(AgendaItem.actions)
        .joinedload(ActionItem.creator),
        selectinload(Meeting.agenda_items)
        .selectinload(AgendaItem.open_questions)
        .joinedload(OpenQuestion.owner_user),
        selectinload(Meeting.agenda_items)
        .selectinload(AgendaItem.open_questions)
        .joinedload(OpenQuestion.creator),
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
        self.session.commit()
        self.session.refresh(series)
        return series

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
            return series

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
        self.session.refresh(series)
        return series

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
            return meeting
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
        try:
            self.session.commit()
        except StaleDataError as exc:
            self._raise_meeting_stale(meeting_id, payload.expected_version, exc)
        self.session.refresh(meeting)
        return meeting

    @staticmethod
    def _invalid_transition(meeting: Meeting, target: MeetingStatus) -> None:
        raise AppError(
            409,
            "invalid_meeting_transition",
            "会议状态不可执行此操作",
            details={"from": meeting.status.value, "to": target.value},
        )

    def _commit_meeting_command(
        self, meeting: Meeting, expected_version: int
    ) -> Meeting:
        meeting_id = meeting.id
        meeting.version += 1
        try:
            self.session.commit()
        except (StaleDataError, IntegrityError) as exc:
            self._raise_meeting_stale(meeting_id, expected_version, exc)
        self.session.refresh(meeting)
        return meeting

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
        return self._commit_meeting_command(meeting, payload.expected_version)

    def start(self, meeting_id: str, payload: LifecycleCommand, actor: User) -> Meeting:
        self._require_active(actor)
        meeting = self.get_meeting(meeting_id)
        require_version(payload.expected_version, meeting.version)
        if meeting.status not in {MeetingStatus.draft, MeetingStatus.ready}:
            self._invalid_transition(meeting, MeetingStatus.in_progress)
        meeting.status = MeetingStatus.in_progress
        meeting.started_at = meeting.started_at or utcnow()
        meeting.updated_by = actor.id
        return self._commit_meeting_command(meeting, payload.expected_version)

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
            return {name: getattr(item, name) for name in names}

        def decision_document(decision):
            result = columns(
                decision,
                (
                    "id",
                    "project_id",
                    "meeting_id",
                    "agenda_item_id",
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
            result["reviewers"] = [
                columns(row, ("user_id", "status", "responded_at", "comment"))
                for row in sorted(decision.reviewers, key=lambda row: row.user_id)
            ]
            return result

        def action_document(row):
            return columns(
                row,
                (
                    "id",
                    "project_id",
                    "meeting_id",
                    "agenda_item_id",
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

        def question_document(row):
            return columns(
                row,
                (
                    "id",
                    "project_id",
                    "meeting_id",
                    "agenda_item_id",
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

    def finish(
        self, meeting_id: str, payload: LifecycleCommand, actor: User
    ) -> Meeting:
        self._require_active(actor)
        meeting = self._meeting_for_snapshot(meeting_id)
        require_version(payload.expected_version, meeting.version)
        if meeting.status != MeetingStatus.in_progress:
            self._invalid_transition(meeting, MeetingStatus.completed)
        unresolved = [
            row.id
            for row in sorted(
                meeting.agenda_items, key=lambda row: (row.position, row.id)
            )
            if row.status in {AgendaStatus.planned, AgendaStatus.in_progress}
        ]
        if unresolved:
            raise AppError(
                409,
                "meeting_has_unresolved_agenda",
                "会议仍有未处理议题",
                details={"agenda_ids": unresolved},
            )
        completion_number = (
            self.session.scalar(
                select(func.max(MeetingSnapshot.completion_number)).where(
                    MeetingSnapshot.meeting_id == meeting.id
                )
            )
            or 0
        ) + 1
        snapshot = MeetingSnapshot(
            meeting_id=meeting.id,
            completion_number=completion_number,
            snapshot_json=self._snapshot_document(meeting),
            created_by=actor.id,
        )
        self.session.add(snapshot)
        meeting.current_snapshot = snapshot
        meeting.status = MeetingStatus.completed
        meeting.completed_at = utcnow()
        meeting.updated_by = actor.id
        return self._commit_meeting_command(meeting, payload.expected_version)

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
        meeting.updated_by = actor.id
        self._commit_meeting_command(meeting, payload.expected_version)
        self.session.refresh(amendment)
        return amendment

    @staticmethod
    def serialize_snapshot(item: MeetingSnapshot) -> dict[str, Any]:
        return {
            "id": item.id,
            "meeting_id": item.meeting_id,
            "completion_number": item.completion_number,
            "snapshot": item.snapshot_json,
            "created_by_user_id": item.created_by,
            "created_by": user_ref(item.creator),
            "created_at": item.created_at,
        }

    @staticmethod
    def serialize_amendment(item: MeetingAmendment) -> dict[str, Any]:
        return {
            "id": item.id,
            "meeting_id": item.meeting_id,
            "reason": item.reason,
            "content_markdown": item.content_markdown,
            "created_by_user_id": item.created_by,
            "created_by": user_ref(item.creator),
            "created_at": item.created_at,
        }

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
                    "decisions": [decision_detail(item) for item in row.decisions],
                    "actions": [action_detail(item) for item in row.actions],
                    "open_questions": [
                        question_detail(item) for item in row.open_questions
                    ],
                }
                for row in meeting.agenda_items
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
                *series_relationship_options(),
            )
            .order_by(
                MeetingSeries.updated_at.desc(), MeetingSeries.title, MeetingSeries.id
            )
        )
        return [self.serialize_series(item) for item in self.session.scalars(statement)]

    def list_meetings(self, project_id: str) -> list[dict[str, Any]]:
        self._project(project_id)
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
        series = self.session.scalar(
            select(MeetingSeries)
            .where(MeetingSeries.id == series_id)
            .options(*series_relationship_options())
        )
        if series is None:
            raise AppError(404, "meeting_series_not_found", "会议系列不存在")
        return self.serialize_series(series)

    def meeting_detail(self, meeting_id: str) -> dict[str, Any]:
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
        return {
            "id": item.id,
            "target_type": item.target_type,
            "target_id": item.target_id,
            "original_name": item.original_name,
            "mime_type": item.mime_type,
            "size": item.size,
            "attachment_type": item.attachment_type,
            "created_by": user_ref(item.creator),
            "created_at": item.created_at,
            "download_url": f"/api/attachments/{item.target_type}/{item.target_id}/{item.id}",
        }

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
        package = self.package(meeting_id)
        # api_version=1 plugins consume the former flat meeting contract. New
        # standalone meetings have no free-form type, so expose a deterministic
        # source kind while keeping the 1.0 API serialization untouched.
        return {
            **package,
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
