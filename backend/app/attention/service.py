from datetime import date, datetime, time, timedelta, timezone
from typing import Any

from sqlalchemy import exists, func, or_, select
from sqlalchemy.orm import Session, joinedload

from app.agendas.models import AgendaItem
from app.auth.models import User
from app.domain.enums import (
    ActionStatus,
    AgendaStatus,
    DecisionReviewerStatus,
    DecisionStatus,
    MeetingStatus,
)
from app.inbox.models import Notification
from app.inbox.service import InboxService
from app.meetings.models import Meeting, MeetingParticipant
from app.outcomes.models import ActionItem, Decision, DecisionReviewer
from app.projects.models import Project

UNREAD_LIMIT = 500
NOTIFICATION_LIMIT = 100
ITEM_LIMIT = 200

SUBJECT_TYPES = {"action_item": "action"}
NOTIFICATION_REASONS = {
    "comment.mention": "comment_mention",
    "comment.reply": "comment_reply",
    "action.assigned": "action_assigned",
    "decision.review_requested": "decision_review_requested",
}
REASON_PRIORITY = {
    "action_overdue": 0,
    "decision_review_pending": 1,
    "action_assigned": 1,
    "decision_review_requested": 1,
    "comment_mention": 2,
    "comment_reply": 2,
    "action_due_soon": 3,
    "meeting_needs_preparation": 3,
    "meeting_upcoming": 4,
}


def _project_ref(project: Project) -> dict[str, str]:
    return {"id": project.id, "name": project.name, "slug": project.slug}


def _item(
    subject_type: str,
    subject_id: str,
    project: Project,
    title: str,
    **values: Any,
) -> dict[str, Any]:
    return {
        "subject_type": subject_type,
        "subject_id": subject_id,
        "project": _project_ref(project),
        "title": title,
        "reasons": [],
        **values,
    }


def _add_reason(item: dict[str, Any], reason: str) -> None:
    if reason not in item["reasons"]:
        item["reasons"].append(reason)


def _temporal_order(item: dict[str, Any]) -> float:
    value = item.get("due_date") or item.get("scheduled_start")
    if isinstance(value, datetime):
        aware = value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value
        return aware.timestamp()
    if isinstance(value, date):
        return datetime.combine(value, time.min, tzinfo=timezone.utc).timestamp()
    return float("inf")


class AttentionService:
    def __init__(self, session: Session):
        self.session = session

    @staticmethod
    def _normalize_subject_type(subject_type: str) -> str:
        return SUBJECT_TYPES.get(subject_type, subject_type)

    def _unread(self, user_id: str) -> tuple[list[Notification], int, bool]:
        unread_count = (
            self.session.scalar(
                select(func.count(Notification.id)).where(
                    Notification.user_id == user_id,
                    Notification.read_at.is_(None),
                )
            )
            or 0
        )
        notifications = list(
            self.session.scalars(
                select(Notification)
                .where(
                    Notification.user_id == user_id,
                    Notification.read_at.is_(None),
                )
                .options(joinedload(Notification.actor))
                .order_by(Notification.id.desc())
                .limit(UNREAD_LIMIT)
            )
        )
        return notifications, unread_count, unread_count > NOTIFICATION_LIMIT

    def _domain_actions(
        self, user_id: str, horizon: date
    ) -> tuple[list[ActionItem], bool]:
        rows = list(
            self.session.scalars(
                select(ActionItem)
                .where(
                    ActionItem.owner_user_id == user_id,
                    ActionItem.status.in_(
                        [ActionStatus.open, ActionStatus.in_progress]
                    ),
                    ActionItem.due_date.is_not(None),
                    ActionItem.due_date <= horizon,
                )
                .options(joinedload(ActionItem.project))
                .order_by(ActionItem.due_date, ActionItem.content, ActionItem.id)
                .limit(ITEM_LIMIT + 1)
            )
        )
        return rows[:ITEM_LIMIT], len(rows) > ITEM_LIMIT

    def _domain_decisions(self, user_id: str) -> tuple[list[Decision], bool]:
        rows = list(
            self.session.scalars(
                select(Decision)
                .join(DecisionReviewer)
                .where(
                    DecisionReviewer.user_id == user_id,
                    DecisionReviewer.status == DecisionReviewerStatus.pending,
                    Decision.status == DecisionStatus.proposed,
                )
                .options(joinedload(Decision.project))
                .order_by(Decision.title, Decision.id)
                .limit(ITEM_LIMIT + 1)
            )
        )
        return rows[:ITEM_LIMIT], len(rows) > ITEM_LIMIT

    def _domain_meetings(
        self, user_id: str, now: datetime, upcoming: datetime
    ) -> tuple[list[tuple[Meeting, bool]], bool]:
        is_participant = exists(
            select(MeetingParticipant.meeting_id).where(
                MeetingParticipant.meeting_id == Meeting.id,
                MeetingParticipant.user_id == user_id,
            )
        )
        needs_preparation = exists(
            select(AgendaItem.id).where(
                AgendaItem.meeting_id == Meeting.id,
                AgendaItem.status.in_([AgendaStatus.planned, AgendaStatus.in_progress]),
            )
        )
        rows = self.session.execute(
            select(Meeting, needs_preparation)
            .where(
                Meeting.scheduled_start >= now,
                Meeting.scheduled_start <= upcoming,
                Meeting.status.in_([MeetingStatus.draft, MeetingStatus.ready]),
                or_(
                    Meeting.host_user_id == user_id,
                    Meeting.recorder_user_id == user_id,
                    is_participant,
                ),
            )
            .options(joinedload(Meeting.project))
            .order_by(Meeting.scheduled_start, Meeting.title, Meeting.id)
            .limit(ITEM_LIMIT + 1)
        ).all()
        return rows[:ITEM_LIMIT], len(rows) > ITEM_LIMIT

    def _load_notification_subjects(
        self, keys: set[tuple[str, str]]
    ) -> dict[tuple[str, str], dict[str, Any]]:
        loaded: dict[tuple[str, str], dict[str, Any]] = {}
        ids_by_type: dict[str, set[str]] = {}
        for subject_type, subject_id in keys:
            ids_by_type.setdefault(subject_type, set()).add(subject_id)

        project_ids = ids_by_type.get("project", set())
        if project_ids:
            for project in self.session.scalars(
                select(Project).where(Project.id.in_(project_ids))
            ):
                loaded[("project", project.id)] = _item(
                    "project", project.id, project, project.name
                )

        meeting_ids = ids_by_type.get("meeting", set())
        if meeting_ids:
            for meeting in self.session.scalars(
                select(Meeting)
                .where(Meeting.id.in_(meeting_ids))
                .options(joinedload(Meeting.project))
            ):
                loaded[("meeting", meeting.id)] = _item(
                    "meeting",
                    meeting.id,
                    meeting.project,
                    meeting.title,
                    scheduled_start=meeting.scheduled_start,
                    status=meeting.status,
                )

        agenda_ids = ids_by_type.get("agenda_item", set())
        if agenda_ids:
            for agenda in self.session.scalars(
                select(AgendaItem)
                .where(AgendaItem.id.in_(agenda_ids))
                .options(joinedload(AgendaItem.meeting).joinedload(Meeting.project))
            ):
                loaded[("agenda_item", agenda.id)] = _item(
                    "agenda_item",
                    agenda.id,
                    agenda.meeting.project,
                    agenda.title,
                    status=agenda.status,
                )

        decision_ids = ids_by_type.get("decision", set())
        if decision_ids:
            for decision in self.session.scalars(
                select(Decision)
                .where(Decision.id.in_(decision_ids))
                .options(joinedload(Decision.project))
            ):
                loaded[("decision", decision.id)] = _item(
                    "decision",
                    decision.id,
                    decision.project,
                    decision.title,
                    status=decision.status,
                )

        action_ids = ids_by_type.get("action", set())
        if action_ids:
            for action in self.session.scalars(
                select(ActionItem)
                .where(ActionItem.id.in_(action_ids))
                .options(joinedload(ActionItem.project))
            ):
                loaded[("action", action.id)] = _item(
                    "action",
                    action.id,
                    action.project,
                    action.content,
                    due_date=action.due_date,
                    status=action.status,
                )
        return loaded

    def for_user(self, user: User, now: datetime | None = None) -> dict[str, Any]:
        current = now or datetime.now(timezone.utc)
        if current.tzinfo is None:
            current = current.replace(tzinfo=timezone.utc)
        today = current.date()
        horizon = today + timedelta(days=7)
        upcoming = current + timedelta(days=7)
        rows: dict[tuple[str, str], dict[str, Any]] = {}

        actions, actions_truncated = self._domain_actions(user.id, horizon)
        for action in actions:
            item = _item(
                "action",
                action.id,
                action.project,
                action.content,
                due_date=action.due_date,
                status=action.status,
            )
            _add_reason(
                item,
                "action_overdue" if action.due_date < today else "action_due_soon",
            )
            rows[("action", action.id)] = item

        decisions, decisions_truncated = self._domain_decisions(user.id)
        for decision in decisions:
            item = _item(
                "decision",
                decision.id,
                decision.project,
                decision.title,
                status=decision.status,
            )
            _add_reason(item, "decision_review_pending")
            rows[("decision", decision.id)] = item

        meetings, meetings_truncated = self._domain_meetings(user.id, current, upcoming)
        for meeting, needs_preparation in meetings:
            item = _item(
                "meeting",
                meeting.id,
                meeting.project,
                meeting.title,
                scheduled_start=meeting.scheduled_start,
                status=meeting.status,
            )
            _add_reason(item, "meeting_upcoming")
            if needs_preparation:
                _add_reason(item, "meeting_needs_preparation")
            rows[("meeting", meeting.id)] = item

        unread, unread_count, unread_truncated = self._unread(user.id)
        notification_reasons: dict[tuple[str, str], list[str]] = {}
        for notification in unread:
            reason = NOTIFICATION_REASONS.get(notification.kind)
            if reason is None:
                continue
            key = (
                self._normalize_subject_type(notification.subject_type),
                notification.subject_id,
            )
            reasons = notification_reasons.setdefault(key, [])
            if reason not in reasons:
                reasons.append(reason)

        missing_keys = set(notification_reasons) - set(rows)
        rows.update(self._load_notification_subjects(missing_keys))
        for key, reasons in notification_reasons.items():
            item = rows.get(key)
            if item is None:
                continue
            for reason in reasons:
                _add_reason(item, reason)

        for item in rows.values():
            item["reasons"].sort(
                key=lambda reason: (REASON_PRIORITY.get(reason, 99), reason)
            )
        ordered = sorted(
            rows.values(),
            key=lambda item: (
                min(REASON_PRIORITY.get(reason, 99) for reason in item["reasons"]),
                _temporal_order(item),
                item["title"].casefold(),
                item["subject_id"],
            ),
        )
        items_truncated = len(ordered) > ITEM_LIMIT
        inbox = InboxService(self.session)
        notifications = [
            inbox.serialize(notification)
            for notification in unread[:NOTIFICATION_LIMIT]
        ]
        return {
            "items": ordered[:ITEM_LIMIT],
            "notifications": notifications,
            "mentions": [
                item for item in notifications if item["kind"] == "comment.mention"
            ],
            "unread_count": unread_count,
            "truncated": any(
                (
                    unread_truncated,
                    actions_truncated,
                    decisions_truncated,
                    meetings_truncated,
                    items_truncated,
                )
            ),
        }
