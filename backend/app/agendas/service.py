from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload
from sqlalchemy.orm.exc import StaleDataError

from app.agendas.models import AgendaItem
from app.agendas.schemas import AgendaCommand, AgendaEdit, AgendaReorder, AgendaWrite
from app.auth.models import User, UserStatus
from app.domain.enums import AgendaStatus, MeetingStatus
from app.domain.versioning import require_version
from app.errors import AppError
from app.meetings.models import Meeting
from app.meetings.service import user_ref


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class AgendaService:
    def __init__(self, session: Session):
        self.session = session

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
        if not changes or all(
            getattr(item, key) == value for key, value in changes.items()
        ):
            return item
        self._users([changes.get("proposer_user_id"), changes.get("presenter_user_id")])
        for field, value in changes.items():
            setattr(item, field, value)
        item.updated_by = actor.id
        item.version += 1
        meeting.updated_by = actor.id
        meeting.version += 1
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
        item.updated_by = actor.id
        item.version += 1
        meeting.updated_by = actor.id
        meeting.version += 1
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

    def skip(self, item_id: str, payload: AgendaCommand, actor: User) -> AgendaItem:
        return self._transition(item_id, payload, actor, AgendaStatus.skipped)

    def cancel(self, item_id: str, payload: AgendaCommand, actor: User) -> AgendaItem:
        return self._transition(item_id, payload, actor, AgendaStatus.canceled)

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
