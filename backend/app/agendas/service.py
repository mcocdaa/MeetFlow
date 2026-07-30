from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload
from sqlalchemy.orm.exc import StaleDataError

from app.agendas.lifecycle import complete_item, start_planned_item
from app.agendas.models import AgendaItem
from app.agendas.outcome_tags import TaggedOutcome, parse_outcome_tags
from app.agendas.schemas import (
    AgendaCommand,
    AgendaEdit,
    AgendaMove,
    AgendaReorder,
    AgendaWrite,
)
from app.auth.models import User, UserStatus
from app.collaboration.activity import ActivityRecorder
from app.domain.enums import AgendaStatus, MeetingStatus, OpenQuestionStatus
from app.domain.versioning import require_version
from app.errors import AppError
from app.meetings.models import Meeting
from app.meetings.service import user_ref
from app.outcomes.models import ActionItem, Decision, OpenQuestion


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def _actual_duration_seconds(item: AgendaItem, finished_at: datetime) -> int:
    if item.started_at is None:
        return 0
    return max(0, int((_aware(finished_at) - _aware(item.started_at)).total_seconds()))


class AgendaService:
    def __init__(self, session: Session):
        self.session = session

    def _record(self, item: AgendaItem, actor: User, event_type: str) -> None:
        ActivityRecorder(self.session).record(
            project_id=item.meeting.project_id,
            meeting_id=item.meeting_id,
            actor_user_id=actor.id,
            event_type=event_type,
            subject_type="agenda_item",
            subject_id=item.id,
            payload={"title": item.title},
        )

    @staticmethod
    def _require_active(actor: User) -> None:
        if actor.status != UserStatus.ACTIVE:
            raise AppError(403, "active_user_required", "账号尚未启用")

    def _meeting(self, meeting_id: str) -> Meeting:
        meeting = self.session.get(Meeting, meeting_id)
        if meeting is None:
            raise AppError(404, "meeting_not_found", "会议不存在")
        return meeting

    @staticmethod
    def _require_mutable(meeting: Meeting) -> None:
        if meeting.status == MeetingStatus.completed:
            raise AppError(409, "meeting_completed", "已完成的会议不可修改")
        if meeting.status not in {
            MeetingStatus.draft,
            MeetingStatus.ready,
            MeetingStatus.in_progress,
        }:
            raise AppError(409, "meeting_immutable", "当前会议状态不可修改议程")

    def _users(self, user_ids: Iterable[str | None]) -> None:
        ids = list(dict.fromkeys(user_id for user_id in user_ids if user_id))
        if not ids:
            return
        users = {
            user.id: user
            for user in self.session.scalars(select(User).where(User.id.in_(ids)))
        }
        missing = [user_id for user_id in ids if user_id not in users]
        if missing:
            raise AppError(
                422,
                "user_not_found",
                "议题关联用户不存在",
                details={"user_ids": missing},
            )

    def get(self, item_id: str) -> AgendaItem:
        item = self.session.get(AgendaItem, item_id)
        if item is None:
            raise AppError(404, "agenda_item_not_found", "议题不存在")
        return item

    def _reconcile_derived_outcomes(
        self, item: AgendaItem, tags: list[TaggedOutcome], actor: User
    ) -> None:
        meeting = item.meeting
        rows = {
            "decision": list(
                self.session.scalars(
                    select(Decision).where(Decision.source_agenda_item_id == item.id)
                )
            ),
            "action": list(
                self.session.scalars(
                    select(ActionItem).where(ActionItem.source_agenda_item_id == item.id)
                )
            ),
            "question": list(
                self.session.scalars(
                    select(OpenQuestion).where(
                        OpenQuestion.source_agenda_item_id == item.id
                    )
                )
            ),
        }
        existing = {
            kind: {row.source_tag_key: row for row in values}
            for kind, values in rows.items()
        }
        requested = {
            kind: {tag.source_tag_key for tag in tags if tag.kind == kind}
            for kind in ("decision", "action", "question")
        }

        for tag in tags:
            row = existing[tag.kind].get(tag.source_tag_key)
            if row is None:
                if tag.kind == "decision":
                    self.session.add(
                        Decision(
                            project_id=meeting.project_id,
                            meeting_id=meeting.id,
                            agenda_item_id=item.id,
                            source_agenda_item_id=item.id,
                            source_tag_key=tag.source_tag_key,
                            title=tag.content,
                            decision_markdown=tag.content,
                            created_by=actor.id,
                        )
                    )
                elif tag.kind == "action":
                    self.session.add(
                        ActionItem(
                            project_id=meeting.project_id,
                            meeting_id=meeting.id,
                            agenda_item_id=item.id,
                            source_agenda_item_id=item.id,
                            source_tag_key=tag.source_tag_key,
                            content=tag.content,
                            created_by=actor.id,
                        )
                    )
                else:
                    self.session.add(
                        OpenQuestion(
                            project_id=meeting.project_id,
                            meeting_id=meeting.id,
                            agenda_item_id=item.id,
                            source_agenda_item_id=item.id,
                            source_tag_key=tag.source_tag_key,
                            question_markdown=tag.content,
                            created_by=actor.id,
                        )
                    )
                continue

            changed = False
            for field, value in (
                ("project_id", meeting.project_id),
                ("meeting_id", meeting.id),
                ("agenda_item_id", item.id),
            ):
                if getattr(row, field) != value:
                    setattr(row, field, value)
                    changed = True
            content_fields = {
                "decision": (("title", tag.content), ("decision_markdown", tag.content)),
                "action": (("content", tag.content),),
                "question": (("question_markdown", tag.content),),
            }
            for field, value in content_fields[tag.kind]:
                if getattr(row, field) != value:
                    setattr(row, field, value)
                    changed = True
            if changed:
                row.version += 1

        for kind, values in rows.items():
            for row in values:
                if row.source_tag_key not in requested[kind]:
                    self.session.delete(row)

    def list(self, meeting_id: str) -> list[AgendaItem]:
        self._meeting(meeting_id)
        return list(
            self.session.scalars(
                select(AgendaItem)
                .where(AgendaItem.meeting_id == meeting_id)
                .order_by(AgendaItem.position, AgendaItem.id)
            )
        )

    def _raise_meeting_stale(
        self, meeting_id: str, expected_version: int, exc: Exception
    ) -> None:
        self.session.rollback()
        row = self.session.execute(
            select(Meeting.version, Meeting.status).where(Meeting.id == meeting_id)
        ).one_or_none()
        if row is None:
            raise AppError(404, "meeting_not_found", "会议不存在") from exc
        actual, status = row
        if status == MeetingStatus.completed:
            raise AppError(409, "meeting_completed", "已完成的会议不可修改") from exc
        if status not in {
            MeetingStatus.draft,
            MeetingStatus.ready,
            MeetingStatus.in_progress,
        }:
            raise AppError(
                409, "meeting_immutable", "当前会议状态不可修改议程"
            ) from exc
        require_version(expected_version, actual)
        raise AppError(409, "version_conflict", "会议议程已更新，请刷新后重试") from exc

    def _raise_item_or_meeting_stale(
        self,
        *,
        item_id: str,
        expected_item_version: int,
        meeting_id: str,
        expected_meeting_version: int,
        exc: Exception,
    ) -> None:
        self.session.rollback()
        row = self.session.execute(
            select(Meeting.version, Meeting.status).where(Meeting.id == meeting_id)
        ).one_or_none()
        if row is None:
            raise AppError(404, "meeting_not_found", "会议不存在") from exc
        actual_meeting_version, status = row
        if status == MeetingStatus.completed:
            raise AppError(409, "meeting_completed", "已完成的会议不可修改") from exc
        if status not in {
            MeetingStatus.draft,
            MeetingStatus.ready,
            MeetingStatus.in_progress,
        }:
            raise AppError(
                409, "meeting_immutable", "当前会议状态不可修改议程"
            ) from exc
        require_version(expected_meeting_version, actual_meeting_version)
        actual_item_version = self.session.scalar(
            select(AgendaItem.version).where(AgendaItem.id == item_id)
        )
        if actual_item_version is None:
            raise AppError(404, "agenda_item_not_found", "议题不存在") from exc
        require_version(expected_item_version, actual_item_version)
        raise AppError(
            409, "version_conflict", "议题或会议已更新，请刷新后重试"
        ) from exc

    def _raise_move_stale(
        self,
        *,
        item_id: str,
        expected_item_version: int,
        source_meeting_id: str,
        expected_source_meeting_version: int,
        target_meeting_id: str,
        expected_target_meeting_version: int,
        exc: Exception,
    ) -> None:
        self.session.rollback()
        source = self._meeting(source_meeting_id)
        target = self._meeting(target_meeting_id)
        self._require_mutable(source)
        self._require_mutable(target)
        require_version(expected_source_meeting_version, source.version)
        require_version(expected_target_meeting_version, target.version)
        actual_item_version = self.session.scalar(
            select(AgendaItem.version).where(AgendaItem.id == item_id)
        )
        if actual_item_version is None:
            raise AppError(404, "agenda_item_not_found", "议题不存在") from exc
        require_version(expected_item_version, actual_item_version)
        raise AppError(
            409, "version_conflict", "议题或会议已更新，请刷新后重试"
        ) from exc

    def create(
        self,
        meeting_id: str,
        payload: AgendaWrite,
        actor: User,
        *,
        expected_meeting_version: int,
    ) -> AgendaItem:
        self._require_active(actor)
        meeting = self._meeting(meeting_id)
        self._require_mutable(meeting)
        require_version(expected_meeting_version, meeting.version)
        tags = parse_outcome_tags(payload.notes_markdown)
        self._users([payload.proposer_user_id, payload.presenter_user_id])
        items = self.list(meeting_id)
        position = (
            len(items)
            if payload.position is None
            else min(payload.position, len(items))
        )
        for item in items[position:]:
            item.position += 1
            item.version += 1
            item.updated_by = actor.id
        values = payload.model_dump(exclude={"position"})
        item = AgendaItem(
            meeting_id=meeting_id,
            **values,
            position=position,
            version=1,
            created_by=actor.id,
            updated_by=actor.id,
        )
        self.session.add(item)
        meeting.version += 1
        meeting.updated_by = actor.id
        try:
            self.session.flush()
            self._reconcile_derived_outcomes(item, tags, actor)
            self._record(item, actor, "agenda.created")
            self.session.commit()
        except StaleDataError as exc:
            self._raise_meeting_stale(meeting_id, expected_meeting_version, exc)
        self.session.refresh(item)
        return item

    def update(self, item_id: str, payload: AgendaEdit, actor: User) -> AgendaItem:
        self._require_active(actor)
        item = self.get(item_id)
        meeting = item.meeting
        meeting_id = meeting.id
        self._require_mutable(meeting)
        expected_meeting_version = meeting.version
        require_version(payload.expected_version, item.version)
        changes = payload.model_dump(exclude={"expected_version"}, exclude_unset=True)
        tags = (
            parse_outcome_tags(changes["notes_markdown"])
            if "notes_markdown" in changes
            else None
        )
        if not changes or all(
            getattr(item, key) == value for key, value in changes.items()
        ):
            return item
        self._users([changes.get("proposer_user_id"), changes.get("presenter_user_id")])
        for field, value in changes.items():
            setattr(item, field, value)
        if tags is not None:
            self._reconcile_derived_outcomes(item, tags, actor)
        item.updated_by = actor.id
        item.version += 1
        meeting.updated_by = actor.id
        meeting.version += 1
        self._record(item, actor, "agenda.updated")
        try:
            self.session.commit()
        except StaleDataError as exc:
            self._raise_item_or_meeting_stale(
                item_id=item_id,
                expected_item_version=payload.expected_version,
                meeting_id=meeting_id,
                expected_meeting_version=expected_meeting_version,
                exc=exc,
            )
        self.session.refresh(item)
        return item

    def reorder(
        self, meeting_id: str, payload: AgendaReorder, actor: User
    ) -> list[AgendaItem]:
        self._require_active(actor)
        meeting = self._meeting(meeting_id)
        self._require_mutable(meeting)
        actual_version = self.session.scalar(
            select(Meeting.version).where(Meeting.id == meeting_id)
        )
        if actual_version is None:
            raise AppError(404, "meeting_not_found", "会议不存在")
        require_version(payload.expected_meeting_version, actual_version)
        items = self.list(meeting_id)
        current_ids = [item.id for item in items]
        if len(payload.ids) != len(set(payload.ids)) or set(payload.ids) != set(
            current_ids
        ):
            raise AppError(
                422, "invalid_agenda_set", "排序必须包含当前会议的全部且唯一议题"
            )
        if payload.ids == current_ids:
            return items
        indexed = {item.id: item for item in items}
        result = [indexed[item_id] for item_id in payload.ids]
        for position, item in enumerate(result):
            if item.position != position:
                item.position = position
                item.version += 1
                item.updated_by = actor.id
        meeting.version += 1
        meeting.updated_by = actor.id
        ActivityRecorder(self.session).record(
            project_id=meeting.project_id,
            meeting_id=meeting.id,
            actor_user_id=actor.id,
            event_type="agenda.reordered",
            subject_type="meeting",
            subject_id=meeting.id,
            payload={"agenda_item_ids": payload.ids},
        )
        try:
            self.session.commit()
        except StaleDataError as exc:
            self._raise_meeting_stale(meeting_id, payload.expected_meeting_version, exc)
        return result

    def _transition(
        self,
        item_id: str,
        payload: AgendaCommand,
        actor: User,
        target: AgendaStatus,
    ) -> AgendaItem:
        self._require_active(actor)
        item = self.get(item_id)
        meeting = item.meeting
        self._require_mutable(meeting)
        meeting_id = meeting.id
        expected_meeting_version = meeting.version
        require_version(payload.expected_version, item.version)
        if item.status not in {AgendaStatus.planned, AgendaStatus.in_progress}:
            raise AppError(409, "invalid_agenda_transition", "议题状态不可再次结束")
        now = utcnow()
        if target == AgendaStatus.completed and item.started_at is None:
            item.started_at = now
        item.status = target
        item.completed_at = now
        item.actual_duration_seconds = _actual_duration_seconds(item, now)
        item.updated_by = actor.id
        item.version += 1
        meeting.updated_by = actor.id
        meeting.version += 1
        event_type = {
            AgendaStatus.completed: "agenda.completed",
            AgendaStatus.skipped: "agenda.skipped",
            AgendaStatus.canceled: "agenda.canceled",
        }[target]
        self._record(item, actor, event_type)
        try:
            self.session.commit()
        except StaleDataError as exc:
            self._raise_item_or_meeting_stale(
                item_id=item_id,
                expected_item_version=payload.expected_version,
                meeting_id=meeting_id,
                expected_meeting_version=expected_meeting_version,
                exc=exc,
            )
        self.session.refresh(item)
        return item

    def complete(self, item_id: str, payload: AgendaCommand, actor: User) -> AgendaItem:
        return self._transition(item_id, payload, actor, AgendaStatus.completed)

    def complete_and_advance(
        self, item_id: str, payload: AgendaCommand, actor: User
    ) -> tuple[AgendaItem, str | None]:
        self._require_active(actor)
        item = self.get(item_id)
        meeting = item.meeting
        self._require_mutable(meeting)
        meeting_id = meeting.id
        expected_meeting_version = meeting.version
        require_version(payload.expected_version, item.version)
        if item.status not in {AgendaStatus.planned, AgendaStatus.in_progress}:
            raise AppError(409, "invalid_agenda_transition", "议题状态不可再次结束")
        now = utcnow()
        complete_item(item, actor_id=actor.id, at=now)
        next_item = next(
            (
                row
                for row in self.list(meeting_id)
                if row.position > item.position and row.status == AgendaStatus.planned
            ),
            None,
        )
        if next_item is not None:
            start_planned_item(next_item, actor_id=actor.id, at=now)
        meeting.updated_by = actor.id
        meeting.version += 1
        self._record(item, actor, "agenda.completed")
        if next_item is not None:
            self._record(next_item, actor, "agenda.started")
        try:
            self.session.commit()
        except StaleDataError as exc:
            self._raise_item_or_meeting_stale(
                item_id=item_id,
                expected_item_version=payload.expected_version,
                meeting_id=meeting_id,
                expected_meeting_version=expected_meeting_version,
                exc=exc,
            )
        self.session.refresh(item)
        return item, next_item.id if next_item is not None else None

    def start(self, item_id: str, payload: AgendaCommand, actor: User) -> AgendaItem:
        self._require_active(actor)
        item = self.get(item_id)
        meeting = item.meeting
        if meeting.status != MeetingStatus.in_progress:
            raise AppError(409, "meeting_not_in_progress", "会议尚未开始")
        expected_meeting_version = meeting.version
        require_version(payload.expected_version, item.version)
        if item.status != AgendaStatus.planned:
            raise AppError(409, "invalid_agenda_transition", "只有待处理议题可以开始")
        start_planned_item(item, actor_id=actor.id, at=utcnow())
        meeting.updated_by = actor.id
        meeting.version += 1
        self._record(item, actor, "agenda.started")
        try:
            self.session.commit()
        except StaleDataError as exc:
            self._raise_item_or_meeting_stale(
                item_id=item_id,
                expected_item_version=payload.expected_version,
                meeting_id=meeting.id,
                expected_meeting_version=expected_meeting_version,
                exc=exc,
            )
        self.session.refresh(item)
        return item

    def skip(self, item_id: str, payload: AgendaCommand, actor: User) -> AgendaItem:
        return self._transition(item_id, payload, actor, AgendaStatus.skipped)

    def cancel(self, item_id: str, payload: AgendaCommand, actor: User) -> AgendaItem:
        return self._transition(item_id, payload, actor, AgendaStatus.canceled)

    def move(self, item_id: str, payload: AgendaMove, actor: User) -> AgendaItem:
        self._require_active(actor)
        item = self.get(item_id)
        source = item.meeting
        target = self._meeting(payload.target_meeting_id)
        source_id = source.id
        target_id = target.id
        if source_id == target_id:
            raise AppError(422, "source_mismatch", "目标会议必须与原会议不同")
        if source.project_id != target.project_id:
            raise AppError(422, "source_mismatch", "议题只能移动到同一项目的会议")
        self._require_mutable(source)
        self._require_mutable(target)
        require_version(payload.expected_version, item.version)
        require_version(payload.expected_source_meeting_version, source.version)
        require_version(payload.expected_target_meeting_version, target.version)
        if item.status not in {AgendaStatus.planned, AgendaStatus.in_progress}:
            raise AppError(409, "invalid_agenda_transition", "已结束的议题不能移动")

        # Imported lazily to avoid a model import cycle.
        from app.outcomes.models import ActionItem, Decision, OpenQuestion

        carried_question = None
        if item.carry_from_open_question_id:
            carried_question = self.session.get(
                OpenQuestion, item.carry_from_open_question_id
            )
            if carried_question is None:
                raise AppError(404, "source_not_found", "来源开放问题不存在")
            if (
                carried_question.project_id != source.project_id
                or carried_question.status != OpenQuestionStatus.scheduled
                or carried_question.scheduled_meeting_id != source_id
            ):
                raise AppError(
                    422,
                    "source_mismatch",
                    "来源开放问题与当前排期不一致",
                )
            earliest = utcnow()
            if carried_question.meeting is not None:
                earliest = max(
                    earliest, _aware(carried_question.meeting.scheduled_start)
                )
            if _aware(target.scheduled_start) <= earliest:
                raise AppError(422, "meeting_not_future", "开放问题只能排入之后的会议")
        if item.copied_from_agenda_item_id:
            duplicate = self.session.scalar(
                select(AgendaItem.id).where(
                    AgendaItem.meeting_id == target.id,
                    AgendaItem.copied_from_agenda_item_id
                    == item.copied_from_agenda_item_id,
                )
            )
            if duplicate:
                raise AppError(409, "agenda_already_copied", "目标会议已有该议题副本")

        source_items = self.list(source_id)
        target_items = self.list(target_id)
        position = (
            len(target_items)
            if payload.position is None
            else min(payload.position, len(target_items))
        )
        for other in source_items:
            if other.id != item.id and other.position > item.position:
                other.position -= 1
                other.version += 1
                other.updated_by = actor.id
        for other in target_items[position:]:
            other.position += 1
            other.version += 1
            other.updated_by = actor.id

        item.meeting_id = target_id
        item.position = position
        item.status = AgendaStatus.planned
        item.started_at = None
        item.completed_at = None
        item.actual_duration_seconds = None
        item.updated_by = actor.id
        item.version += 1

        if carried_question is not None:
            carried_question.scheduled_meeting_id = target_id
            carried_question.version += 1

        # Moving the agenda preserves each outcome's agenda source while keeping
        # its denormalized meeting source chain internally consistent.
        for model in (Decision, ActionItem, OpenQuestion):
            for outcome in self.session.scalars(
                select(model).where(model.agenda_item_id == item.id)
            ):
                outcome.meeting_id = target_id
                if outcome is not carried_question:
                    outcome.version += 1

        source.version += 1
        source.updated_by = actor.id
        target.version += 1
        target.updated_by = actor.id
        self._record(item, actor, "agenda.moved")
        try:
            self.session.commit()
        except StaleDataError as exc:
            self._raise_move_stale(
                item_id=item.id,
                expected_item_version=payload.expected_version,
                source_meeting_id=source_id,
                expected_source_meeting_version=payload.expected_source_meeting_version,
                target_meeting_id=target_id,
                expected_target_meeting_version=payload.expected_target_meeting_version,
                exc=exc,
            )
        self.session.refresh(item)
        return item

    def delete(
        self,
        item_id: str,
        payload: AgendaCommand,
        actor: User,
        *,
        expected_meeting_version: int,
    ) -> None:
        self._require_active(actor)
        item = self.get(item_id)
        meeting = item.meeting
        meeting_id = meeting.id
        self._require_mutable(meeting)
        require_version(payload.expected_version, item.version)
        require_version(expected_meeting_version, meeting.version)
        # Imported lazily to avoid a model/service import cycle.
        from app.outcomes.service import OutcomeService

        if OutcomeService(self.session).count_for_agenda(item.id):
            raise AppError(409, "agenda_has_outcomes", "议题已有产出，不能直接删除")
        from app.attachments.models import Attachment

        has_attachment = self.session.scalar(
            select(Attachment.id)
            .where(
                Attachment.target_type == "agenda_item",
                Attachment.target_id == item.id,
            )
            .limit(1)
        )
        if has_attachment:
            raise AppError(409, "agenda_has_attachments", "议题已有附件，不能直接删除")
        from app.collaboration.models import Comment

        has_comment = self.session.scalar(
            select(Comment.id)
            .where(
                Comment.target_type == "agenda_item",
                Comment.target_id == item.id,
            )
            .limit(1)
        )
        if has_comment:
            raise AppError(409, "agenda_has_comments", "议题已有评论，不能直接删除")
        following = list(
            self.session.scalars(
                select(AgendaItem).where(
                    AgendaItem.meeting_id == meeting.id,
                    AgendaItem.position > item.position,
                )
            )
        )
        self.session.delete(item)
        for other in following:
            other.position -= 1
            other.version += 1
            other.updated_by = actor.id
        meeting.version += 1
        meeting.updated_by = actor.id
        self._record(item, actor, "agenda.deleted")
        try:
            self.session.commit()
        except StaleDataError as exc:
            self._raise_meeting_stale(meeting_id, expected_meeting_version, exc)

    def serialize(self, item: AgendaItem) -> dict[str, Any]:
        return {
            "id": item.id,
            "meeting_id": item.meeting_id,
            "title": item.title,
            "agenda_type": item.agenda_type,
            "proposer": user_ref(item.proposer),
            "presenter": user_ref(item.presenter),
            "estimated_minutes": item.estimated_minutes,
            "notes_markdown": item.notes_markdown,
            "status": item.status,
            "position": item.position,
            "carry_from_open_question_id": item.carry_from_open_question_id,
            "copied_from_agenda_item_id": item.copied_from_agenda_item_id,
            "version": item.version,
            "created_by": user_ref(item.creator),
            "updated_by": user_ref(item.updater),
            "created_at": item.created_at,
            "updated_at": item.updated_at,
            "started_at": item.started_at,
            "completed_at": item.completed_at,
        }

    def detail(self, item_id: str) -> dict[str, Any]:
        item = self.session.scalar(
            select(AgendaItem)
            .where(AgendaItem.id == item_id)
            .options(
                joinedload(AgendaItem.proposer),
                joinedload(AgendaItem.presenter),
                joinedload(AgendaItem.creator),
                joinedload(AgendaItem.updater),
            )
        )
        if item is None:
            raise AppError(404, "agenda_item_not_found", "议题不存在")
        return self.serialize(item)

    def ordered_detail(self, meeting_id: str) -> list[dict[str, Any]]:
        items = self.session.scalars(
            select(AgendaItem)
            .where(AgendaItem.meeting_id == meeting_id)
            .options(
                joinedload(AgendaItem.proposer),
                joinedload(AgendaItem.presenter),
                joinedload(AgendaItem.creator),
                joinedload(AgendaItem.updater),
            )
            .order_by(AgendaItem.position, AgendaItem.id)
        )
        return [self.serialize(item) for item in items]
