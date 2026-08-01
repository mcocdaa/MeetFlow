from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.auth.models import User, UserRole, UserStatus
from app.domain.enums import ProjectMemberRole
from app.errors import AppError
from app.meetings.models import Meeting, MeetingParticipant
from app.projects.models import Project, ProjectMember


@dataclass(frozen=True)
class WorkspaceCapabilities:
    can_view: bool = False
    can_manage: bool = False
    can_contribute: bool = False
    can_comment: bool = False


class WorkspaceAccess:
    def __init__(self, session: Session):
        self.session = session

    @staticmethod
    def _require_active(actor: User) -> None:
        if actor.status != UserStatus.ACTIVE:
            raise AppError(403, "active_user_required", "账号尚未启用")

    def _project(self, project_id: str) -> Project:
        project = self.session.scalar(
            select(Project)
            .where(Project.id == project_id)
            .options(selectinload(Project.memberships))
        )
        if project is None:
            raise AppError(404, "project_not_found", "项目不存在")
        return project

    def _meeting(self, meeting_id: str) -> Meeting:
        meeting = self.session.get(Meeting, meeting_id)
        if meeting is None:
            raise AppError(404, "meeting_not_found", "会议不存在")
        return meeting

    def project_capabilities(
        self, project: Project, actor: User
    ) -> WorkspaceCapabilities:
        if actor.status != UserStatus.ACTIVE:
            return WorkspaceCapabilities()
        if actor.role == UserRole.ADMIN or project.lead_user_id == actor.id:
            return WorkspaceCapabilities(True, True, True, True)
        membership = next(
            (row for row in project.memberships if row.user_id == actor.id), None
        )
        if membership is None:
            return WorkspaceCapabilities()
        if membership.role == ProjectMemberRole.member:
            return WorkspaceCapabilities(True, False, True, True)
        return WorkspaceCapabilities(True, False, False, False)

    def meeting_capabilities(
        self, meeting: Meeting, actor: User
    ) -> WorkspaceCapabilities:
        project_capabilities = self.project_capabilities(
            self._project(meeting.project_id), actor
        )
        if project_capabilities.can_view:
            return project_capabilities
        invited = self.session.scalar(
            select(MeetingParticipant.user_id).where(
                MeetingParticipant.meeting_id == meeting.id,
                MeetingParticipant.user_id == actor.id,
            )
        )
        return WorkspaceCapabilities(can_view=invited is not None, can_comment=invited is not None)

    def visible_project_ids(self, actor: User):
        self._require_active(actor)
        if actor.role == UserRole.ADMIN:
            return None
        return select(ProjectMember.project_id).where(
            ProjectMember.user_id == actor.id
        ).union(select(Project.id).where(Project.lead_user_id == actor.id))

    def _require_project_capability(
        self,
        project_id: str,
        actor: User,
        capability: str,
        error_code: str,
        message: str,
    ) -> Project:
        self._require_active(actor)
        project = self._project(project_id)
        if not getattr(self.project_capabilities(project, actor), capability):
            raise AppError(403, error_code, message)
        return project

    def require_project_view(self, project_id: str, actor: User) -> Project:
        return self._require_project_capability(
            project_id,
            actor,
            "can_view",
            "project_view_forbidden",
            "无权查看此项目",
        )

    def require_project_contribute(self, project_id: str, actor: User) -> Project:
        return self._require_project_capability(
            project_id,
            actor,
            "can_contribute",
            "project_contribution_forbidden",
            "无权修改此项目内容",
        )

    def require_project_manage(self, project_id: str, actor: User) -> Project:
        return self._require_project_capability(
            project_id,
            actor,
            "can_manage",
            "project_management_forbidden",
            "无权管理此项目",
        )

    def require_meeting_view(self, meeting_id: str, actor: User) -> Meeting:
        self._require_active(actor)
        meeting = self._meeting(meeting_id)
        if not self.meeting_capabilities(meeting, actor).can_view:
            raise AppError(403, "project_view_forbidden", "无权查看此会议")
        return meeting

    def require_meeting_comment(self, meeting_id: str, actor: User) -> Meeting:
        self._require_active(actor)
        meeting = self._meeting(meeting_id)
        if not self.meeting_capabilities(meeting, actor).can_comment:
            raise AppError(403, "meeting_comment_forbidden", "无权评论此会议")
        return meeting
