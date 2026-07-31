from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Iterable

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload
from sqlalchemy.orm.exc import StaleDataError

from app.agendas.models import AgendaItem
from app.auth.models import User, UserStatus
from app.collaboration.activity import ActivityRecorder
from app.domain.enums import (
    ActionPriority,
    ActionStatus,
    AgendaStatus,
    DecisionStatus,
    MeetingStatus,
    OpenQuestionStatus,
)
from app.domain.versioning import require_version
from app.errors import AppError
from app.inbox.service import NotificationWriter
from app.meetings.models import Meeting
from app.outcomes.models import (
    ActionItem,
    Decision,
    DecisionReviewer,
    OpenQuestion,
    OutcomeMigrationRecord,
)
from app.outcomes.schemas import (
    ActionEdit,
    ActionWrite,
    AgendaCopyWrite,
    AgendaConvertWrite,
    AgendaOutcomeMigrationWrite,
    DecisionEdit,
    DecisionFinalizeWrite,
    DecisionReviewWrite,
    DecisionSupersedeWrite,
    DecisionWrite,
    QuestionEdit,
    QuestionResolveWrite,
    QuestionScheduleWrite,
    QuestionWrite,
)
from app.projects.models import Project


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


class OutcomeService:
    def __init__(self, session: Session):
        self.session = session

    def _record(
        self,
        *,
        project_id: str,
        meeting_id: str | None,
        actor: User,
        event_type: str,
        subject_type: str,
        subject_id: str,
        payload: dict[str, Any],
    ) -> None:
        ActivityRecorder(self.session).record(
            project_id=project_id,
            meeting_id=meeting_id,
            actor_user_id=actor.id,
            event_type=event_type,
            subject_type=subject_type,
            subject_id=subject_id,
            payload=payload,
        )

    def _notify_action_assignment(self, action: ActionItem, actor: User) -> None:
        if action.owner_user_id is None:
            return
        NotificationWriter(self.session).add(
            user_id=action.owner_user_id,
            actor_user_id=actor.id,
            project_id=action.project_id,
            meeting_id=action.meeting_id,
            kind="action.assigned",
            subject_type="action_item",
            subject_id=action.id,
            source_comment_id=None,
            data={
                "owner_user_id": action.owner_user_id,
                "version": action.version,
            },
            dedupe_key=(
                f"action-assigned:{action.id}:{action.owner_user_id}:{action.version}"
            ),
        )

    def _notify_decision_review(
        self, decision: Decision, actor: User, reviewer_ids: Iterable[str]
    ) -> None:
        writer = NotificationWriter(self.session)
        for reviewer_id in reviewer_ids:
            writer.add(
                user_id=reviewer_id,
                actor_user_id=actor.id,
                project_id=decision.project_id,
                meeting_id=decision.meeting_id,
                kind="decision.review_requested",
                subject_type="decision",
                subject_id=decision.id,
                source_comment_id=None,
                data={"version": decision.version},
                dedupe_key=(
                    f"decision-review:{decision.id}:{reviewer_id}:{decision.version}"
                ),
            )

    @staticmethod
    def _action_payload(action: ActionItem) -> dict[str, Any]:
        return {
            "status": action.status.value,
            "owner_user_id": action.owner_user_id,
            "due_date": action.due_date.isoformat() if action.due_date else None,
        }

    @staticmethod
    def _question_payload(question: OpenQuestion) -> dict[str, Any]:
        return {
            "status": question.status.value,
            "owner_user_id": question.owner_user_id,
            "scheduled_meeting_id": question.scheduled_meeting_id,
        }

    @staticmethod
    def _require_active(actor: User) -> None:
        if actor.status != UserStatus.ACTIVE:
            raise AppError(403, "active_user_required", "账号尚未启用")

    def _project(self, project_id: str) -> Project:
        project = self.session.get(Project, project_id)
        if project is None:
            raise AppError(404, "source_not_found", "项目或会议来源不存在")
        return project

    def _users(self, user_ids: Iterable[str | None]) -> None:
        ids = list(dict.fromkeys(value for value in user_ids if value))
        if not ids:
            return
        found = {
            user.id: user
            for user in self.session.scalars(select(User).where(User.id.in_(ids)))
        }
        missing = [value for value in ids if value not in found]
        inactive = [
            value
            for value in ids
            if value in found and found[value].status != UserStatus.ACTIVE
        ]
        if missing or inactive:
            raise AppError(
                422,
                "user_not_found",
                "关联用户不存在或未启用",
                details={"user_ids": missing + inactive},
            )

    def require_source_chain(
        self,
        project_id: str,
        meeting_id: str | None,
        agenda_item_id: str | None,
    ) -> tuple[Project, Meeting | None, AgendaItem | None]:
        project = self._project(project_id)
        meeting = self.session.get(Meeting, meeting_id) if meeting_id else None
        agenda = (
            self.session.get(AgendaItem, agenda_item_id) if agenda_item_id else None
        )
        if (meeting_id and meeting is None) or (agenda_item_id and agenda is None):
            raise AppError(404, "source_not_found", "项目或会议来源不存在")
        if meeting is not None and meeting.project_id != project.id:
            raise AppError(422, "source_mismatch", "会议来源与项目不匹配")
        if agenda is not None and (meeting is None or agenda.meeting_id != meeting.id):
            raise AppError(422, "source_mismatch", "议题来源与会议不匹配")
        if meeting is not None:
            self._mutable_meeting(meeting)
        return project, meeting, agenda

    def _commit(
        self,
        *,
        entity: str = "outcome",
        model: type | None = None,
        entity_id: str | None = None,
        expected_version: int | None = None,
        meeting_versions: dict[str, int] | None = None,
    ) -> None:
        try:
            self.session.commit()
        except StaleDataError as exc:
            self.session.rollback()
            for meeting_id, expected_meeting_version in (
                meeting_versions or {}
            ).items():
                actual_meeting_version = self.session.scalar(
                    select(Meeting.version).where(Meeting.id == meeting_id)
                )
                if actual_meeting_version is not None:
                    require_version(expected_meeting_version, actual_meeting_version)
            if (
                model is not None
                and entity_id is not None
                and expected_version is not None
            ):
                actual = self.session.scalar(
                    select(model.version).where(model.id == entity_id)
                )
                if actual is not None:
                    require_version(expected_version, actual)
            raise AppError(
                409, "version_conflict", f"{entity}已更新，请刷新后重试"
            ) from exc

    def _touch_meetings(self, actor: User, *meeting_ids: str | None) -> dict[str, int]:
        expected: dict[str, int] = {}
        for meeting_id in dict.fromkeys(value for value in meeting_ids if value):
            meeting = self.session.get(Meeting, meeting_id)
            if meeting is None:
                raise AppError(404, "source_not_found", "会议来源不存在")
            expected[meeting.id] = meeting.version
            meeting.version += 1
            meeting.updated_by = actor.id
        return expected

    def _decision(self, decision_id: str) -> Decision:
        decision = self.session.scalar(
            select(Decision)
            .where(Decision.id == decision_id)
            .options(selectinload(Decision.reviewers))
        )
        if decision is None:
            raise AppError(404, "decision_not_found", "决策不存在")
        return decision

    def create_decision(
        self, project_id: str, payload: DecisionWrite, actor: User
    ) -> Decision:
        self._require_active(actor)
        _, meeting, _ = self.require_source_chain(
            project_id, payload.meeting_id, payload.agenda_item_id
        )
        self._users(payload.reviewer_ids)
        decision = Decision(
            project_id=project_id,
            meeting_id=payload.meeting_id,
            agenda_item_id=payload.agenda_item_id,
            title=payload.title,
            decision_markdown=payload.decision_markdown,
            rationale_markdown=payload.rationale_markdown,
            created_by=actor.id,
            reviewers=[
                DecisionReviewer(user_id=value) for value in payload.reviewer_ids
            ],
        )
        self.session.add(decision)
        self.session.flush()
        self._record(
            project_id=decision.project_id,
            meeting_id=decision.meeting_id,
            actor=actor,
            event_type="decision.created",
            subject_type="decision",
            subject_id=decision.id,
            payload={"title": decision.title},
        )
        self._notify_decision_review(decision, actor, payload.reviewer_ids)
        meeting_versions = self._touch_meetings(actor, meeting.id if meeting else None)
        self._commit(entity="决策", meeting_versions=meeting_versions)
        return self._decision(decision.id)

    def update_decision(
        self, decision_id: str, payload: DecisionEdit, actor: User
    ) -> Decision:
        self._require_active(actor)
        decision = self._decision(decision_id)
        if decision.source_agenda_item_id is not None:
            raise AppError(409, "derived_outcome_read_only", "议题备注生成的成果不可直接编辑")
        require_version(payload.expected_version, decision.version)
        if decision.status != DecisionStatus.proposed:
            raise AppError(409, "decision_immutable", "仅提议中的决策可编辑")
        changes = payload.model_dump(
            exclude={"expected_version", "reviewer_ids"}, exclude_unset=True
        )
        reviewer_ids = (
            payload.reviewer_ids if "reviewer_ids" in payload.model_fields_set else None
        )
        existing_reviewer_ids = {row.user_id for row in decision.reviewers}
        if reviewer_ids is not None:
            self._users(reviewer_ids)
            existing = {row.user_id: row for row in decision.reviewers}
            selected = [
                existing.get(value) or DecisionReviewer(user_id=value)
                for value in reviewer_ids
            ]
            retained_ids = set(reviewer_ids)
            selected.extend(
                row
                for row in decision.reviewers
                if row.user_id not in retained_ids and row.responded_at is not None
            )
            decision.reviewers = selected
        for key, value in changes.items():
            setattr(decision, key, value)
        if changes or reviewer_ids is not None:
            meeting_versions = self._touch_meetings(actor, decision.meeting_id)
            decision.version += 1
            self._record(
                project_id=decision.project_id,
                meeting_id=decision.meeting_id,
                actor=actor,
                event_type="decision.updated",
                subject_type="decision",
                subject_id=decision.id,
                payload={"title": decision.title},
            )
            if reviewer_ids is not None:
                self._notify_decision_review(
                    decision,
                    actor,
                    set(reviewer_ids) - existing_reviewer_ids,
                )
            self._commit(
                entity="决策",
                model=Decision,
                entity_id=decision.id,
                expected_version=payload.expected_version,
                meeting_versions=meeting_versions,
            )
        return self._decision(decision.id)

    def review_decision(
        self, decision_id: str, payload: DecisionReviewWrite, actor: User
    ) -> Decision:
        self._require_active(actor)
        decision = self._decision(decision_id)
        require_version(payload.expected_version, decision.version)
        if decision.status != DecisionStatus.proposed:
            raise AppError(409, "decision_not_reviewable", "决策已不再接受评审")
        reviewer = next(
            (row for row in decision.reviewers if row.user_id == actor.id), None
        )
        if reviewer is None:
            raise AppError(
                403, "decision_reviewer_required", "只有指定评审人可提交评审"
            )
        reviewer.status = payload.status
        reviewer.comment = payload.comment
        reviewer.responded_at = utcnow()
        meeting_versions = self._touch_meetings(actor, decision.meeting_id)
        decision.version += 1
        self._record(
            project_id=decision.project_id,
            meeting_id=decision.meeting_id,
            actor=actor,
            event_type="decision.reviewed",
            subject_type="decision",
            subject_id=decision.id,
            payload={"title": decision.title, "status": payload.status},
        )
        self._commit(
            entity="决策",
            model=Decision,
            entity_id=decision.id,
            expected_version=payload.expected_version,
            meeting_versions=meeting_versions,
        )
        return self._decision(decision.id)

    def finalize_decision(
        self, decision_id: str, payload: DecisionFinalizeWrite, actor: User
    ) -> Decision:
        self._require_active(actor)
        decision = self._decision(decision_id)
        require_version(payload.expected_version, decision.version)
        if decision.status != DecisionStatus.proposed:
            raise AppError(409, "invalid_decision_transition", "仅提议中的决策可定稿")
        decision.status = DecisionStatus.final
        decision.decided_by_user_id = actor.id
        meeting_versions = self._touch_meetings(actor, decision.meeting_id)
        decision.version += 1
        self._record(
            project_id=decision.project_id,
            meeting_id=decision.meeting_id,
            actor=actor,
            event_type="decision.finalized",
            subject_type="decision",
            subject_id=decision.id,
            payload={"title": decision.title},
        )
        self._commit(
            entity="决策",
            model=Decision,
            entity_id=decision.id,
            expected_version=payload.expected_version,
            meeting_versions=meeting_versions,
        )
        return self._decision(decision.id)

    def withdraw_decision(
        self, decision_id: str, payload: DecisionFinalizeWrite, actor: User
    ) -> Decision:
        self._require_active(actor)
        decision = self._decision(decision_id)
        require_version(payload.expected_version, decision.version)
        if decision.status != DecisionStatus.proposed:
            raise AppError(409, "invalid_decision_transition", "仅提议中的决策可撤回")
        decision.status = DecisionStatus.withdrawn
        meeting_versions = self._touch_meetings(actor, decision.meeting_id)
        decision.version += 1
        self._record(
            project_id=decision.project_id,
            meeting_id=decision.meeting_id,
            actor=actor,
            event_type="decision.withdrawn",
            subject_type="decision",
            subject_id=decision.id,
            payload={"title": decision.title},
        )
        self._commit(
            entity="决策",
            model=Decision,
            entity_id=decision.id,
            expected_version=payload.expected_version,
            meeting_versions=meeting_versions,
        )
        return self._decision(decision.id)

    def supersede_decision(
        self, decision_id: str, payload: DecisionSupersedeWrite, actor: User
    ) -> Decision:
        self._require_active(actor)
        old = self._decision(decision_id)
        new = self._decision(payload.new_decision_id)
        require_version(payload.expected_version, old.version)
        require_version(payload.expected_new_version, new.version)
        if (
            old.project_id != new.project_id
            or old.status != DecisionStatus.final
            or new.status != DecisionStatus.final
        ):
            raise AppError(
                422, "invalid_supersession", "仅同项目的最终决策可建立替代关系"
            )
        if old.id == new.id or new.supersedes_decision_id is not None:
            raise AppError(409, "decision_already_supersedes", "新决策已建立替代关系")
        old.status = DecisionStatus.superseded
        old.version += 1
        new.supersedes_decision_id = old.id
        new.version += 1
        meeting_versions = self._touch_meetings(actor, old.meeting_id, new.meeting_id)
        self._record(
            project_id=old.project_id,
            meeting_id=old.meeting_id,
            actor=actor,
            event_type="decision.superseded",
            subject_type="decision",
            subject_id=old.id,
            payload={"title": old.title, "replacement_id": new.id},
        )
        self._commit(entity="决策", meeting_versions=meeting_versions)
        return self._decision(new.id)

    def _action(self, action_id: str) -> ActionItem:
        action = self.session.get(ActionItem, action_id)
        if action is None:
            raise AppError(404, "action_not_found", "行动项不存在")
        return action

    def create_action(
        self, project_id: str, payload: ActionWrite, actor: User
    ) -> ActionItem:
        self._require_active(actor)
        if payload.project_id != project_id:
            raise AppError(422, "source_mismatch", "行动项项目与路径项目不匹配")
        _, meeting, _ = self.require_source_chain(
            project_id, payload.meeting_id, payload.agenda_item_id
        )
        self._users([payload.owner_user_id])
        values = payload.model_dump(exclude={"project_id"})
        values["priority"] = ActionPriority(payload.priority)
        action = ActionItem(
            project_id=project_id,
            **values,
            created_by=actor.id,
        )
        self.session.add(action)
        self.session.flush()
        self._record(
            project_id=action.project_id,
            meeting_id=action.meeting_id,
            actor=actor,
            event_type="action.created",
            subject_type="action_item",
            subject_id=action.id,
            payload=self._action_payload(action),
        )
        self._notify_action_assignment(action, actor)
        meeting_versions = self._touch_meetings(actor, meeting.id if meeting else None)
        self._commit(entity="行动项", meeting_versions=meeting_versions)
        self.session.refresh(action)
        return action

    def update_action(
        self, action_id: str, payload: ActionEdit, actor: User
    ) -> ActionItem:
        self._require_active(actor)
        action = self._action(action_id)
        if action.source_agenda_item_id is not None:
            raise AppError(409, "derived_outcome_read_only", "议题备注生成的成果不可直接编辑")
        require_version(payload.expected_version, action.version)
        previous_owner_user_id = action.owner_user_id
        requested = payload.model_dump(exclude={"expected_version"}, exclude_unset=True)
        changes = {
            key: value
            for key, value in requested.items()
            if getattr(action, key) != value
        }
        if "owner_user_id" in changes:
            self._users([changes["owner_user_id"]])
        previous_status = action.status
        for key, value in changes.items():
            setattr(action, key, value)
        if "status" in changes:
            if changes["status"] == ActionStatus.done:
                action.completed_at = utcnow()
            elif previous_status == ActionStatus.done:
                action.completed_at = None
        if changes:
            meeting_versions = self._touch_meetings(actor, action.meeting_id)
            action.version += 1
            event_type = "action.updated"
            if "status" in changes:
                event_type = (
                    "action.completed"
                    if changes["status"] == ActionStatus.done
                    else (
                        "action.reopened"
                        if previous_status == ActionStatus.done
                        else "action.status_changed"
                    )
                )
            self._record(
                project_id=action.project_id,
                meeting_id=action.meeting_id,
                actor=actor,
                event_type=event_type,
                subject_type="action_item",
                subject_id=action.id,
                payload=self._action_payload(action),
            )
            if (
                "owner_user_id" in changes
                and action.owner_user_id != previous_owner_user_id
            ):
                self._notify_action_assignment(action, actor)
            self._commit(
                entity="行动项",
                model=ActionItem,
                entity_id=action.id,
                expected_version=payload.expected_version,
                meeting_versions=meeting_versions,
            )
        self.session.refresh(action)
        return action

    def _question(self, question_id: str) -> OpenQuestion:
        question = self.session.get(OpenQuestion, question_id)
        if question is None:
            raise AppError(404, "question_not_found", "开放问题不存在")
        return question

    def create_question(
        self, project_id: str, payload: QuestionWrite, actor: User
    ) -> OpenQuestion:
        self._require_active(actor)
        _, meeting, _ = self.require_source_chain(
            project_id, payload.meeting_id, payload.agenda_item_id
        )
        self._users([payload.owner_user_id])
        question = OpenQuestion(
            project_id=project_id, **payload.model_dump(), created_by=actor.id
        )
        self.session.add(question)
        self.session.flush()
        self._record(
            project_id=question.project_id,
            meeting_id=question.meeting_id,
            actor=actor,
            event_type="question.created",
            subject_type="open_question",
            subject_id=question.id,
            payload=self._question_payload(question),
        )
        meeting_versions = self._touch_meetings(actor, meeting.id if meeting else None)
        self._commit(entity="开放问题", meeting_versions=meeting_versions)
        self.session.refresh(question)
        return question

    def update_question(
        self, question_id: str, payload: QuestionEdit, actor: User
    ) -> OpenQuestion:
        self._require_active(actor)
        question = self._question(question_id)
        if question.source_agenda_item_id is not None:
            raise AppError(409, "derived_outcome_read_only", "议题备注生成的成果不可直接编辑")
        require_version(payload.expected_version, question.version)
        changes = payload.model_dump(exclude={"expected_version"}, exclude_unset=True)
        if "owner_user_id" in changes:
            self._users([changes["owner_user_id"]])
        for key, value in changes.items():
            setattr(question, key, value)
        if changes:
            meeting_versions = self._touch_meetings(actor, question.meeting_id)
            question.version += 1
            self._record(
                project_id=question.project_id,
                meeting_id=question.meeting_id,
                actor=actor,
                event_type="question.updated",
                subject_type="open_question",
                subject_id=question.id,
                payload=self._question_payload(question),
            )
            self._commit(
                entity="开放问题",
                model=OpenQuestion,
                entity_id=question.id,
                expected_version=payload.expected_version,
                meeting_versions=meeting_versions,
            )
        return question

    @staticmethod
    def _mutable_meeting(meeting: Meeting) -> None:
        if meeting.status not in {
            MeetingStatus.draft,
            MeetingStatus.ready,
            MeetingStatus.in_progress,
        }:
            raise AppError(409, "meeting_immutable", "目标会议不可修改")

    def schedule_question(
        self, question_id: str, payload: QuestionScheduleWrite, actor: User
    ) -> AgendaItem:
        self._require_active(actor)
        question = self._question(question_id)
        require_version(payload.expected_version, question.version)
        if (
            question.status == OpenQuestionStatus.scheduled
            or question.scheduled_meeting_id
        ):
            raise AppError(409, "question_already_scheduled", "开放问题已排入会议")
        if question.status != OpenQuestionStatus.open:
            raise AppError(409, "question_not_open", "开放问题当前不可排期")
        meeting = self.session.get(Meeting, payload.meeting_id)
        if meeting is None:
            raise AppError(404, "source_not_found", "目标会议不存在")
        require_version(payload.expected_meeting_version, meeting.version)
        self._mutable_meeting(meeting)
        if meeting.project_id != question.project_id:
            raise AppError(422, "source_mismatch", "目标会议与开放问题不属于同一项目")
        origin = question.meeting
        earliest = utcnow()
        if origin is not None:
            earliest = max(earliest, _aware(origin.scheduled_start))
        if _aware(meeting.scheduled_start) <= earliest:
            raise AppError(422, "meeting_not_future", "开放问题只能排入之后的会议")
        position = (
            self.session.scalar(
                select(func.count())
                .select_from(AgendaItem)
                .where(AgendaItem.meeting_id == meeting.id)
            )
            or 0
        )
        item = AgendaItem(
            meeting_id=meeting.id,
            title=question.question_markdown[:300],
            notes_markdown=question.question_markdown,
            position=position,
            carry_from_open_question_id=question.id,
            created_by=actor.id,
            updated_by=actor.id,
        )
        self.session.add(item)
        question.status = OpenQuestionStatus.scheduled
        question.scheduled_meeting_id = meeting.id
        question.version += 1
        meeting_versions = self._touch_meetings(actor, question.meeting_id, meeting.id)
        self._record(
            project_id=question.project_id,
            meeting_id=meeting.id,
            actor=actor,
            event_type="question.scheduled",
            subject_type="open_question",
            subject_id=question.id,
            payload=self._question_payload(question),
        )
        self._commit(entity="开放问题或会议", meeting_versions=meeting_versions)
        self.session.refresh(item)
        return item

    def resolve_question(
        self, question_id: str, payload: QuestionResolveWrite, actor: User
    ) -> OpenQuestion:
        self._require_active(actor)
        question = self._question(question_id)
        require_version(payload.expected_version, question.version)
        if question.status in {OpenQuestionStatus.resolved, OpenQuestionStatus.dropped}:
            raise AppError(409, "question_already_closed", "开放问题已关闭")
        if payload.decision_id:
            decision = self._decision(payload.decision_id)
            if (
                decision.project_id != question.project_id
                or decision.status != DecisionStatus.final
            ):
                raise AppError(
                    422, "invalid_resolution_decision", "只能关联同项目的最终决策"
                )
        question.status = OpenQuestionStatus.resolved
        question.resolved_by_decision_id = payload.decision_id
        meeting_versions = self._touch_meetings(actor, question.meeting_id)
        question.version += 1
        self._record(
            project_id=question.project_id,
            meeting_id=question.meeting_id,
            actor=actor,
            event_type="question.resolved",
            subject_type="open_question",
            subject_id=question.id,
            payload=self._question_payload(question),
        )
        self._commit(
            entity="开放问题",
            model=OpenQuestion,
            entity_id=question.id,
            expected_version=payload.expected_version,
            meeting_versions=meeting_versions,
        )
        return question

    def count_for_agenda(self, agenda_id: str) -> int:
        return sum(
            self.session.scalar(
                select(func.count())
                .select_from(model)
                .where(model.agenda_item_id == agenda_id)
            )
            or 0
            for model in (Decision, ActionItem, OpenQuestion)
        )

    def migrate_agenda_outcomes(
        self, source_id: str, payload: AgendaOutcomeMigrationWrite, actor: User
    ) -> AgendaItem:
        self._require_active(actor)
        source = self.session.get(AgendaItem, source_id)
        target = self.session.get(AgendaItem, payload.target_agenda_item_id)
        if source is None or target is None:
            raise AppError(404, "source_not_found", "源议题或目标议题不存在")
        actual_source_version = self.session.scalar(
            select(AgendaItem.version).where(AgendaItem.id == source.id)
        )
        actual_target_version = self.session.scalar(
            select(AgendaItem.version).where(AgendaItem.id == target.id)
        )
        require_version(payload.expected_source_version, actual_source_version)
        require_version(payload.expected_target_version, actual_target_version)
        if source.id == target.id:
            raise AppError(422, "source_mismatch", "源议题与目标议题不能相同")
        if source.meeting.project_id != target.meeting.project_id:
            raise AppError(422, "source_mismatch", "议题不属于同一项目")
        source_meeting = source.meeting
        target_meeting = target.meeting
        self._mutable_meeting(source_meeting)
        if target_meeting.id != source_meeting.id:
            self._mutable_meeting(target_meeting)
        actual_source_meeting_version = self.session.scalar(
            select(Meeting.version).where(Meeting.id == source_meeting.id)
        )
        actual_target_meeting_version = self.session.scalar(
            select(Meeting.version).where(Meeting.id == target_meeting.id)
        )
        require_version(
            payload.expected_source_meeting_version,
            actual_source_meeting_version,
        )
        require_version(
            payload.expected_target_meeting_version,
            actual_target_meeting_version,
        )
        moved_rows: list[dict[str, Any]] = []
        model_types = (
            (Decision, "decision"),
            (ActionItem, "action"),
            (OpenQuestion, "open_question"),
        )
        for model, outcome_type in model_types:
            for outcome in self.session.scalars(
                select(model).where(
                    model.agenda_item_id == source.id,
                    model.source_agenda_item_id.is_(None),
                )
            ):
                moved_rows.append(
                    {
                        "type": outcome_type,
                        "id": outcome.id,
                        "old_agenda_item_id": outcome.agenda_item_id,
                        "old_meeting_id": outcome.meeting_id,
                    }
                )
                outcome.agenda_item_id = target.id
                outcome.meeting_id = target.meeting_id
                outcome.version += 1
        if not moved_rows:
            raise AppError(409, "agenda_has_no_outcomes", "源议题没有可迁移产物")
        self.session.add(
            OutcomeMigrationRecord(
                source_agenda_id=source.id,
                source_meeting_id=source.meeting_id,
                target_agenda_id=target.id,
                target_meeting_id=target.meeting_id,
                moved_outcomes_json=moved_rows,
                created_by=actor.id,
            )
        )
        source.version += 1
        source.updated_by = actor.id
        target.version += 1
        target.updated_by = actor.id
        meeting_versions = self._touch_meetings(
            actor, source_meeting.id, target_meeting.id
        )
        self._record(
            project_id=source_meeting.project_id,
            meeting_id=source_meeting.id,
            actor=actor,
            event_type="agenda.outcomes_migrated",
            subject_type="agenda_item",
            subject_id=source.id,
            payload={
                "target_agenda_item_id": target.id,
                "target_meeting_id": target.meeting_id,
                "outcome_ids": [row["id"] for row in moved_rows],
            },
        )
        self._commit(entity="议题产物", meeting_versions=meeting_versions)
        return target

    def convert_agenda_to_question(
        self, source_id: str, payload: AgendaConvertWrite, actor: User
    ) -> OpenQuestion:
        self._require_active(actor)
        source = self.session.get(AgendaItem, source_id)
        if source is None:
            raise AppError(404, "source_not_found", "源议题不存在")
        existing = self.session.scalar(
            select(OpenQuestion).where(
                OpenQuestion.converted_from_agenda_item_id == source.id
            )
        )
        if existing is not None:
            raise AppError(409, "agenda_already_converted", "议题已转为开放问题")
        require_version(payload.expected_source_version, source.version)
        source_meeting = source.meeting
        require_version(payload.expected_source_meeting_version, source_meeting.version)
        self._mutable_meeting(source_meeting)
        if source.status != AgendaStatus.skipped:
            raise AppError(409, "agenda_not_skipped", "只有跳过的议题可转为开放问题")
        question = OpenQuestion(
            id=str(uuid.uuid4()),
            project_id=source_meeting.project_id,
            meeting_id=source.meeting_id,
            agenda_item_id=source.id,
            converted_from_agenda_item_id=source.id,
            question_markdown=source.title,
            created_by=actor.id,
        )
        self.session.add(question)
        source.version += 1
        source.updated_by = actor.id
        source_meeting_id = source_meeting.id
        self._touch_meetings(actor, source_meeting.id)
        try:
            self._record(
                project_id=question.project_id,
                meeting_id=question.meeting_id,
                actor=actor,
                event_type="agenda.converted_to_question",
                subject_type="open_question",
                subject_id=question.id,
                payload={"source_agenda_item_id": source.id},
            )
            self.session.commit()
        except IntegrityError as exc:
            self.session.rollback()
            duplicate = self.session.scalar(
                select(OpenQuestion.id).where(
                    OpenQuestion.converted_from_agenda_item_id == source_id
                )
            )
            if duplicate is not None:
                raise AppError(
                    409, "agenda_already_converted", "议题已转为开放问题"
                ) from exc
            raise AppError(
                409,
                "outcome_integrity_conflict",
                "开放问题写入违反数据完整性约束",
            ) from exc
        except StaleDataError as exc:
            self.session.rollback()
            actual_source = self.session.scalar(
                select(AgendaItem.version).where(AgendaItem.id == source_id)
            )
            if actual_source is not None:
                require_version(payload.expected_source_version, actual_source)
            actual_meeting = self.session.scalar(
                select(Meeting.version).where(Meeting.id == source_meeting_id)
            )
            if actual_meeting is not None:
                require_version(payload.expected_source_meeting_version, actual_meeting)
            raise AppError(409, "version_conflict", "议题或会议已更新") from exc
        self.session.refresh(question)
        return question

    def copy_agenda_to_meeting(
        self, source_id: str, payload: AgendaCopyWrite, actor: User
    ) -> AgendaItem:
        self._require_active(actor)
        source = self.session.get(AgendaItem, source_id)
        target = self.session.get(Meeting, payload.target_meeting_id)
        if source is None or target is None:
            raise AppError(404, "source_not_found", "源议题或目标会议不存在")
        duplicate = self.session.scalar(
            select(AgendaItem).where(
                AgendaItem.meeting_id == target.id,
                AgendaItem.copied_from_agenda_item_id == source.id,
            )
        )
        if duplicate is not None:
            raise AppError(409, "agenda_already_copied", "议题已复制到目标会议")
        require_version(payload.expected_source_version, source.version)
        source_meeting = source.meeting
        require_version(payload.expected_source_meeting_version, source_meeting.version)
        require_version(payload.expected_target_meeting_version, target.version)
        if source.status != AgendaStatus.skipped:
            raise AppError(409, "agenda_not_skipped", "只有跳过的议题可复制")
        self._mutable_meeting(source_meeting)
        self._mutable_meeting(target)
        if target.project_id != source_meeting.project_id:
            raise AppError(422, "source_mismatch", "目标会议不属于同一项目")
        if _aware(target.scheduled_start) <= max(
            utcnow(), _aware(source_meeting.scheduled_start)
        ):
            raise AppError(422, "meeting_not_future", "议题只能复制到之后的会议")
        question = self.session.scalar(
            select(OpenQuestion).where(
                OpenQuestion.converted_from_agenda_item_id == source.id
            )
        )
        carry_id = question.id if question is not None else None
        position = (
            self.session.scalar(
                select(func.count())
                .select_from(AgendaItem)
                .where(AgendaItem.meeting_id == target.id)
            )
            or 0
        )
        item = AgendaItem(
            id=str(uuid.uuid4()),
            meeting_id=target.id,
            title=source.title,
            agenda_type=source.agenda_type,
            proposer_user_id=source.proposer_user_id,
            presenter_user_id=source.presenter_user_id,
            estimated_minutes=source.estimated_minutes,
            notes_markdown=source.notes_markdown,
            position=position,
            carry_from_open_question_id=carry_id,
            copied_from_agenda_item_id=source.id,
            created_by=actor.id,
            updated_by=actor.id,
        )
        self.session.add(item)
        source.version += 1
        source.updated_by = actor.id
        source_meeting_id = source_meeting.id
        self._touch_meetings(actor, source_meeting.id, target.id)
        try:
            self._record(
                project_id=target.project_id,
                meeting_id=target.id,
                actor=actor,
                event_type="agenda.copied",
                subject_type="agenda_item",
                subject_id=item.id,
                payload={
                    "source_agenda_item_id": source.id,
                    "source_meeting_id": source_meeting.id,
                },
            )
            self.session.commit()
        except IntegrityError as exc:
            self.session.rollback()
            duplicate = self.session.scalar(
                select(AgendaItem.id).where(
                    AgendaItem.meeting_id == payload.target_meeting_id,
                    AgendaItem.copied_from_agenda_item_id == source_id,
                )
            )
            if duplicate is not None:
                raise AppError(
                    409, "agenda_already_copied", "议题已复制到目标会议"
                ) from exc
            raise AppError(
                409,
                "outcome_integrity_conflict",
                "复制议题违反数据完整性约束",
            ) from exc
        except StaleDataError as exc:
            self.session.rollback()
            actual_source = self.session.scalar(
                select(AgendaItem.version).where(AgendaItem.id == source_id)
            )
            if actual_source is not None:
                require_version(payload.expected_source_version, actual_source)
            actual_source_meeting = self.session.scalar(
                select(Meeting.version).where(Meeting.id == source_meeting_id)
            )
            if actual_source_meeting is not None:
                require_version(
                    payload.expected_source_meeting_version,
                    actual_source_meeting,
                )
            actual_target = self.session.scalar(
                select(Meeting.version).where(Meeting.id == payload.target_meeting_id)
            )
            if actual_target is not None:
                require_version(payload.expected_target_meeting_version, actual_target)
            raise AppError(409, "version_conflict", "议题或会议已更新") from exc
        self.session.refresh(item)
        return item

    def list_decisions(self, project_id: str, limit: int = 200) -> list[Decision]:
        self._project(project_id)
        return list(
            self.session.scalars(
                select(Decision)
                .where(Decision.project_id == project_id)
                .options(selectinload(Decision.reviewers))
                .order_by(Decision.updated_at.desc(), Decision.id)
                .limit(limit)
            )
        )

    def list_actions(self, project_id: str, limit: int = 200) -> list[ActionItem]:
        self._project(project_id)
        return list(
            self.session.scalars(
                select(ActionItem)
                .where(ActionItem.project_id == project_id)
                .order_by(ActionItem.updated_at.desc(), ActionItem.id)
                .limit(limit)
            )
        )

    def list_questions(self, project_id: str, limit: int = 200) -> list[OpenQuestion]:
        self._project(project_id)
        return list(
            self.session.scalars(
                select(OpenQuestion)
                .where(OpenQuestion.project_id == project_id)
                .order_by(OpenQuestion.updated_at.desc(), OpenQuestion.id)
                .limit(limit)
            )
        )

    def list_migration_records(
        self, agenda_id: str, limit: int = 200
    ) -> list[OutcomeMigrationRecord]:
        return list(
            self.session.scalars(
                select(OutcomeMigrationRecord)
                .where(
                    (OutcomeMigrationRecord.source_agenda_id == agenda_id)
                    | (OutcomeMigrationRecord.target_agenda_id == agenda_id)
                )
                .order_by(
                    OutcomeMigrationRecord.created_at.desc(),
                    OutcomeMigrationRecord.id,
                )
                .limit(min(max(limit, 1), 200))
            )
        )

    @staticmethod
    def serialize(item: Any) -> dict[str, Any]:
        result = {
            column.name: getattr(item, column.name) for column in item.__table__.columns
        }
        result["is_derived"] = item.source_agenda_item_id is not None
        if isinstance(item, Decision):
            result["reviewers"] = [
                {
                    "user_id": row.user_id,
                    "status": row.status,
                    "responded_at": row.responded_at,
                    "comment": row.comment,
                }
                for row in item.reviewers
            ]
        return result
