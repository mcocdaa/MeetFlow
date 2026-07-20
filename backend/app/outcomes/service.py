from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload
from sqlalchemy.orm.exc import StaleDataError

from app.agendas.models import AgendaItem
from app.auth.models import User, UserStatus
from app.domain.enums import (
    ActionStatus,
    AgendaStatus,
    DecisionStatus,
    MeetingStatus,
    OpenQuestionStatus,
)
from app.domain.versioning import require_version
from app.errors import AppError
from app.meetings.models import Meeting
from app.outcomes.models import ActionItem, Decision, DecisionReviewer, OpenQuestion
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
        return project, meeting, agenda

    def _commit(
        self,
        *,
        entity: str = "outcome",
        model: type | None = None,
        entity_id: str | None = None,
        expected_version: int | None = None,
    ) -> None:
        try:
            self.session.commit()
        except StaleDataError as exc:
            self.session.rollback()
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
        self.require_source_chain(
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
        self._commit(entity="决策")
        return self._decision(decision.id)

    def update_decision(
        self, decision_id: str, payload: DecisionEdit, actor: User
    ) -> Decision:
        self._require_active(actor)
        decision = self._decision(decision_id)
        require_version(payload.expected_version, decision.version)
        if decision.status != DecisionStatus.proposed:
            raise AppError(409, "decision_immutable", "仅提议中的决策可编辑")
        changes = payload.model_dump(
            exclude={"expected_version", "reviewer_ids"}, exclude_unset=True
        )
        reviewer_ids = (
            payload.reviewer_ids if "reviewer_ids" in payload.model_fields_set else None
        )
        if reviewer_ids is not None:
            self._users(reviewer_ids)
            existing = {row.user_id: row for row in decision.reviewers}
            decision.reviewers = [
                existing.get(value) or DecisionReviewer(user_id=value)
                for value in reviewer_ids
            ]
        for key, value in changes.items():
            setattr(decision, key, value)
        if changes or reviewer_ids is not None:
            decision.version += 1
            self._commit(
                entity="决策",
                model=Decision,
                entity_id=decision.id,
                expected_version=payload.expected_version,
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
        decision.version += 1
        self._commit(
            entity="决策",
            model=Decision,
            entity_id=decision.id,
            expected_version=payload.expected_version,
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
        decision.version += 1
        self._commit(
            entity="决策",
            model=Decision,
            entity_id=decision.id,
            expected_version=payload.expected_version,
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
        decision.version += 1
        self._commit(
            entity="决策",
            model=Decision,
            entity_id=decision.id,
            expected_version=payload.expected_version,
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
        self._commit(entity="决策")
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
        self.require_source_chain(
            project_id, payload.meeting_id, payload.agenda_item_id
        )
        self._users([payload.owner_user_id])
        action = ActionItem(
            project_id=project_id, **payload.model_dump(), created_by=actor.id
        )
        self.session.add(action)
        self._commit(entity="行动项")
        self.session.refresh(action)
        return action

    def update_action(
        self, action_id: str, payload: ActionEdit, actor: User
    ) -> ActionItem:
        self._require_active(actor)
        action = self._action(action_id)
        require_version(payload.expected_version, action.version)
        changes = payload.model_dump(exclude={"expected_version"}, exclude_unset=True)
        if "owner_user_id" in changes:
            self._users([changes["owner_user_id"]])
        for key, value in changes.items():
            setattr(action, key, value)
        if "status" in changes:
            action.completed_at = (
                utcnow() if changes["status"] == ActionStatus.done else None
            )
        if changes:
            action.version += 1
            self._commit(
                entity="行动项",
                model=ActionItem,
                entity_id=action.id,
                expected_version=payload.expected_version,
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
        self.require_source_chain(
            project_id, payload.meeting_id, payload.agenda_item_id
        )
        self._users([payload.owner_user_id])
        question = OpenQuestion(
            project_id=project_id, **payload.model_dump(), created_by=actor.id
        )
        self.session.add(question)
        self._commit(entity="开放问题")
        self.session.refresh(question)
        return question

    def update_question(
        self, question_id: str, payload: QuestionEdit, actor: User
    ) -> OpenQuestion:
        self._require_active(actor)
        question = self._question(question_id)
        require_version(payload.expected_version, question.version)
        changes = payload.model_dump(exclude={"expected_version"}, exclude_unset=True)
        if "owner_user_id" in changes:
            self._users([changes["owner_user_id"]])
        for key, value in changes.items():
            setattr(question, key, value)
        if changes:
            question.version += 1
            self._commit(
                entity="开放问题",
                model=OpenQuestion,
                entity_id=question.id,
                expected_version=payload.expected_version,
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
        if origin is not None and _aware(meeting.scheduled_start) <= _aware(
            origin.scheduled_start
        ):
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
        meeting.version += 1
        meeting.updated_by = actor.id
        self._commit(entity="开放问题或会议")
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
        question.version += 1
        self._commit(
            entity="开放问题",
            model=OpenQuestion,
            entity_id=question.id,
            expected_version=payload.expected_version,
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
        require_version(payload.expected_source_version, source.version)
        require_version(payload.expected_target_version, target.version)
        if source.id == target.id:
            raise AppError(422, "source_mismatch", "源议题与目标议题不能相同")
        if source.meeting.project_id != target.meeting.project_id:
            raise AppError(422, "source_mismatch", "议题不属于同一项目")
        source_meeting = source.meeting
        target_meeting = target.meeting
        require_version(payload.expected_source_meeting_version, source_meeting.version)
        require_version(payload.expected_target_meeting_version, target_meeting.version)
        moved = 0
        for model in (Decision, ActionItem, OpenQuestion):
            for outcome in self.session.scalars(
                select(model).where(model.agenda_item_id == source.id)
            ):
                outcome.agenda_item_id = target.id
                outcome.meeting_id = target.meeting_id
                outcome.version += 1
                moved += 1
        if not moved:
            raise AppError(409, "agenda_has_no_outcomes", "源议题没有可迁移产物")
        source.version += 1
        source.updated_by = actor.id
        target.version += 1
        target.updated_by = actor.id
        source_meeting.version += 1
        source_meeting.updated_by = actor.id
        if target_meeting.id != source_meeting.id:
            target_meeting.version += 1
            target_meeting.updated_by = actor.id
        self._commit(entity="议题产物")
        return target

    def convert_agenda_to_question(
        self, source_id: str, payload: AgendaConvertWrite, actor: User
    ) -> OpenQuestion:
        self._require_active(actor)
        source = self.session.get(AgendaItem, source_id)
        if source is None:
            raise AppError(404, "source_not_found", "源议题不存在")
        require_version(payload.expected_source_version, source.version)
        if source.status != AgendaStatus.skipped:
            raise AppError(409, "agenda_not_skipped", "只有跳过的议题可转为开放问题")
        existing = self.session.scalar(
            select(OpenQuestion).where(OpenQuestion.agenda_item_id == source.id)
        )
        if existing is not None:
            raise AppError(409, "agenda_already_converted", "议题已转为开放问题")
        question = OpenQuestion(
            project_id=source.meeting.project_id,
            meeting_id=source.meeting_id,
            agenda_item_id=source.id,
            question_markdown=source.title,
            created_by=actor.id,
        )
        self.session.add(question)
        self._commit(entity="开放问题")
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
        require_version(payload.expected_source_version, source.version)
        require_version(payload.expected_target_meeting_version, target.version)
        if source.status != AgendaStatus.skipped:
            raise AppError(409, "agenda_not_skipped", "只有跳过的议题可复制")
        self._mutable_meeting(target)
        if target.project_id != source.meeting.project_id:
            raise AppError(422, "source_mismatch", "目标会议不属于同一项目")
        if _aware(target.scheduled_start) <= _aware(source.meeting.scheduled_start):
            raise AppError(422, "meeting_not_future", "议题只能复制到之后的会议")
        question = self.session.scalar(
            select(OpenQuestion).where(OpenQuestion.agenda_item_id == source.id)
        )
        carry_id = question.id if question is not None else None
        duplicate = self.session.scalar(
            select(AgendaItem).where(
                AgendaItem.meeting_id == target.id,
                AgendaItem.title == source.title,
                AgendaItem.carry_from_open_question_id == carry_id,
            )
        )
        if duplicate is not None:
            raise AppError(409, "agenda_already_copied", "议题已复制到目标会议")
        position = (
            self.session.scalar(
                select(func.count())
                .select_from(AgendaItem)
                .where(AgendaItem.meeting_id == target.id)
            )
            or 0
        )
        item = AgendaItem(
            meeting_id=target.id,
            title=source.title,
            agenda_type=source.agenda_type,
            proposer_user_id=source.proposer_user_id,
            presenter_user_id=source.presenter_user_id,
            estimated_minutes=source.estimated_minutes,
            notes_markdown=source.notes_markdown,
            position=position,
            carry_from_open_question_id=carry_id,
            created_by=actor.id,
            updated_by=actor.id,
        )
        self.session.add(item)
        target.version += 1
        target.updated_by = actor.id
        self._commit(entity="会议议题")
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

    @staticmethod
    def serialize(item: Any) -> dict[str, Any]:
        result = {
            column.name: getattr(item, column.name) for column in item.__table__.columns
        }
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
