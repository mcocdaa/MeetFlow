from dataclasses import dataclass

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.auth.models import User
from app.inbox.models import Notification
from app.meetings.models import MeetingParticipant
from app.projects.access import WorkspaceAccess


@dataclass(frozen=True)
class NotificationScope:
    project_ids: set[str] | None
    participant_meeting_ids: set[str]

    @classmethod
    def for_user(cls, session: Session, user: User) -> "NotificationScope":
        access = WorkspaceAccess(session)
        visible_project_ids = access.visible_project_ids(user)
        project_ids = (
            None
            if visible_project_ids is None
            else set(session.scalars(visible_project_ids))
        )
        participant_meeting_ids = set(
            session.scalars(
                select(MeetingParticipant.meeting_id).where(
                    MeetingParticipant.user_id == user.id
                )
            )
        )
        return cls(project_ids, participant_meeting_ids)

    def project_visible(self, project_id: str | None) -> bool:
        return project_id is not None and (
            self.project_ids is None or project_id in self.project_ids
        )

    def meeting_visible(self, project_id: str | None, meeting_id: str | None) -> bool:
        return self.project_visible(project_id) or (
            meeting_id is not None and meeting_id in self.participant_meeting_ids
        )

    def notification_filter(self):
        if self.project_ids is None:
            return None
        project_visible = Notification.project_id.in_(self.project_ids)
        meeting_visible = Notification.meeting_id.in_(self.participant_meeting_ids)
        return or_(
            and_(
                Notification.project_id.is_(None),
                Notification.meeting_id.is_(None),
            ),
            and_(
                Notification.project_id.is_not(None),
                project_visible,
            ),
            and_(
                Notification.meeting_id.is_not(None),
                meeting_visible,
            ),
        )
