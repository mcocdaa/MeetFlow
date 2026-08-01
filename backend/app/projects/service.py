from __future__ import annotations

from typing import Any

from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload, selectinload
from sqlalchemy.orm.exc import StaleDataError

from app.auth.models import User, UserRole, UserStatus
from app.collaboration.activity import ActivityRecorder
from app.domain.versioning import require_version
from app.errors import AppError
from app.meetings.models import Meeting
from app.meetings.models import MeetingSeries
from app.attachments.models import Attachment
from app.outcomes.models import ActionItem, Decision
from app.outcomes.service import OutcomeService
from app.projects.models import Project, ProjectMember, ProjectUpdate
from app.projects.access import WorkspaceAccess
from app.projects.schemas import ProjectEdit, ProjectUpdateWrite, ProjectWrite


def user_ref(user: User | None) -> dict[str, str] | None:
    if user is None:
        return None
    return {
        "id": user.id,
        "username": user.username,
        "display_name": user.display_name,
        "avatar_color": user.avatar_color,
    }


def unique_ids(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))


class ProjectService:
    def __init__(self, session: Session):
        self.session = session

    def require(self, project_id: str) -> Project:
        project = self.session.get(Project, project_id)
        if project is None:
            raise AppError(404, "project_not_found", "项目不存在")
        return project

    def require_update(self, update_id: str) -> ProjectUpdate:
        update = self.session.get(ProjectUpdate, update_id)
        if update is None:
            raise AppError(404, "project_update_not_found", "项目进展不存在")
        return update

    @staticmethod
    def _require_active(actor: User) -> None:
        if actor.status != UserStatus.ACTIVE:
            raise AppError(403, "active_user_required", "账号尚未启用")

    def _users(self, user_ids: list[str]) -> dict[str, User]:
        ids = unique_ids(user_ids)
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
                "项目成员不存在",
                details={"user_ids": missing},
            )
        return users

    def _validate_user_references(
        self, lead_user_id: str | None, member_ids: list[str]
    ) -> list[str]:
        members = unique_ids(member_ids)
        references = members + ([lead_user_id] if lead_user_id else [])
        self._users(references)
        return members

    @staticmethod
    def _memberships(member_ids: list[str]) -> list[ProjectMember]:
        return [
            ProjectMember(user_id=user_id, position=position)
            for position, user_id in enumerate(member_ids)
        ]

    def create(self, payload: ProjectWrite, actor: User) -> Project:
        self._require_active(actor)
        member_ids = self._validate_user_references(
            payload.lead_user_id, unique_ids([*payload.member_ids, actor.id])
        )
        values = payload.model_dump(exclude={"member_ids"})
        project = Project(
            **values,
            version=1,
            created_by=actor.id,
            updated_by=actor.id,
            memberships=self._memberships(member_ids),
        )
        self.session.add(project)
        try:
            self.session.flush()
            ActivityRecorder(self.session).record(
                project_id=project.id,
                actor_user_id=actor.id,
                event_type="project.created",
                subject_type="project",
                subject_id=project.id,
                payload={"name": project.name},
            )
            self.session.commit()
        except IntegrityError as exc:
            self.session.rollback()
            raise AppError(
                409,
                "project_slug_taken",
                "项目标识已存在",
                details={"slug": payload.slug},
            ) from exc
        self.session.refresh(project)
        return project

    def update(self, project_id: str, payload: ProjectEdit, actor: User) -> Project:
        project = WorkspaceAccess(self.session).require_project_manage(
            project_id, actor
        )
        require_version(payload.expected_version, project.version)
        changes = payload.model_dump(
            exclude={"expected_version", "member_ids"}, exclude_unset=True
        )
        member_ids = payload.member_ids
        if not changes and member_ids is None:
            return project
        lead_id = changes.get("lead_user_id", project.lead_user_id)
        if member_ids is not None:
            member_ids = self._validate_user_references(lead_id, member_ids)
        elif "lead_user_id" in changes:
            self._validate_user_references(lead_id, [])

        for field, value in changes.items():
            setattr(project, field, value)
        if member_ids is not None:
            project.memberships = self._memberships(member_ids)
        project.updated_by = actor.id
        project.version += 1
        ActivityRecorder(self.session).record(
            project_id=project.id,
            actor_user_id=actor.id,
            event_type="project.updated",
            subject_type="project",
            subject_id=project.id,
            payload={"name": project.name},
        )
        try:
            self.session.commit()
        except StaleDataError as exc:
            self.session.rollback()
            actual_version = self.session.scalar(
                select(Project.version).where(Project.id == project_id)
            )
            if actual_version is None:
                raise AppError(404, "project_not_found", "项目不存在") from exc
            require_version(payload.expected_version, actual_version)
            raise AppError(
                409,
                "version_conflict",
                "项目已被其他操作更新，请刷新后重试",
                details={
                    "expected_version": payload.expected_version,
                    "actual_version": actual_version,
                },
            ) from exc
        except IntegrityError as exc:
            self.session.rollback()
            raise AppError(
                409,
                "project_slug_taken",
                "项目标识已存在",
                details={"slug": changes.get("slug", project.slug)},
            ) from exc
        self.session.refresh(project)
        return project

    def create_update(
        self,
        project_id: str,
        payload: ProjectUpdateWrite,
        actor: User,
    ) -> ProjectUpdate:
        project = WorkspaceAccess(self.session).require_project_contribute(
            project_id, actor
        )
        update = ProjectUpdate(
            project_id=project.id,
            created_by=actor.id,
            **payload.model_dump(),
        )
        self.session.add(update)
        self.session.flush()
        ActivityRecorder(self.session).record(
            project_id=project.id,
            actor_user_id=actor.id,
            event_type="project.progress_posted",
            subject_type="project_update",
            subject_id=update.id,
            payload={"health": update.health.value},
        )
        self.session.commit()
        self.session.refresh(update)
        return update

    def edit_update(
        self,
        update_id: str,
        payload: ProjectUpdateWrite,
        actor: User,
    ) -> ProjectUpdate:
        update = self.require_update(update_id)
        WorkspaceAccess(self.session).require_project_contribute(
            update.project_id, actor
        )
        if update.created_by != actor.id and actor.role != UserRole.ADMIN:
            raise AppError(
                403,
                "project_update_forbidden",
                "只能修改自己发布的项目进展",
            )
        for field, value in payload.model_dump().items():
            setattr(update, field, value)
        ActivityRecorder(self.session).record(
            project_id=update.project_id,
            actor_user_id=actor.id,
            event_type="project.progress_updated",
            subject_type="project_update",
            subject_id=update.id,
            payload={"health": update.health.value},
        )
        self.session.commit()
        self.session.refresh(update)
        return update

    def delete(self, project_id: str, actor: User) -> None:
        try:
            project = WorkspaceAccess(self.session).require_project_manage(
                project_id, actor
            )
        except AppError as exc:
            if exc.code != "project_management_forbidden":
                raise
            raise AppError(
                403,
                "project_delete_forbidden",
                "只有管理员或项目负责人可以删除项目",
            ) from exc
        has_meeting = self.session.scalar(
            select(Meeting.id).where(Meeting.project_id == project.id).limit(1)
        )
        if has_meeting:
            raise AppError(
                409,
                "project_not_empty",
                "项目下已有会议，不能删除",
            )
        has_attachment = self.session.scalar(
            select(Attachment.id)
            .where(
                Attachment.target_type == "project",
                Attachment.target_id == project.id,
            )
            .limit(1)
        )
        if has_attachment:
            raise AppError(409, "project_has_attachments", "项目已有附件，不能删除")
        ActivityRecorder(self.session).record(
            project_id=project.id,
            actor_user_id=actor.id,
            event_type="project.deleted",
            subject_type="project",
            subject_id=project.id,
            payload={"name": project.name},
        )
        self.session.delete(project)
        self.session.commit()

    def serialize_update(self, update: ProjectUpdate) -> dict[str, Any]:
        return {
            "id": update.id,
            "project_id": update.project_id,
            "health": update.health,
            "content_markdown": update.content_markdown,
            "source": update.source,
            "created_by": user_ref(update.creator),
            "created_at": update.created_at,
            "updated_at": update.updated_at,
        }

    def _updates(
        self, project_id: str, *, limit: int, offset: int = 0
    ) -> list[ProjectUpdate]:
        statement = (
            select(ProjectUpdate)
            .where(ProjectUpdate.project_id == project_id)
            .options(joinedload(ProjectUpdate.creator))
            .order_by(ProjectUpdate.created_at.desc(), ProjectUpdate.id.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(self.session.scalars(statement))

    def serialize(
        self,
        project: Project,
        *,
        updates: list[ProjectUpdate] | None = None,
        actor: User | None = None,
    ) -> dict[str, Any]:
        if updates is None:
            updates = self._updates(project.id, limit=20)
        result = {
            "id": project.id,
            "name": project.name,
            "slug": project.slug,
            "summary": project.summary,
            "description_markdown": project.description_markdown,
            "status": project.status,
            "health": project.health,
            "lead": user_ref(project.lead),
            "target_date": project.target_date,
            "version": project.version,
            "memberships": [
                {
                    "role": membership.role,
                    "user": user_ref(membership.user),
                }
                for membership in project.memberships
            ],
            "updates": [self.serialize_update(update) for update in updates],
            "created_by": user_ref(project.creator),
            "updated_by": user_ref(project.updater),
            "created_at": project.created_at,
            "updated_at": project.updated_at,
        }
        if actor is not None:
            capabilities = WorkspaceAccess(self.session).project_capabilities(
                project, actor
            )
            result["capabilities"] = {
                "can_manage": capabilities.can_manage,
                "can_contribute": capabilities.can_contribute,
                "can_comment": capabilities.can_comment,
            }
        return result

    def list(self, actor: User) -> list[dict[str, Any]]:
        access = WorkspaceAccess(self.session)
        statement = (
            select(Project)
            .options(
                joinedload(Project.lead),
                joinedload(Project.creator),
                joinedload(Project.updater),
                selectinload(Project.memberships).joinedload(ProjectMember.user),
            )
            .order_by(Project.updated_at.desc())
        )
        visible_project_ids = access.visible_project_ids(actor)
        if visible_project_ids is not None:
            statement = statement.where(Project.id.in_(visible_project_ids))
        projects = self.session.scalars(statement)
        return [self.serialize(project, updates=[]) for project in projects]

    def detail(self, project_id: str, actor: User) -> dict[str, Any]:
        WorkspaceAccess(self.session).require_project_view(project_id, actor)
        statement = (
            select(Project)
            .where(Project.id == project_id)
            .options(
                joinedload(Project.lead),
                joinedload(Project.creator),
                joinedload(Project.updater),
                selectinload(Project.memberships).joinedload(ProjectMember.user),
            )
        )
        project = self.session.scalar(statement)
        if project is None:
            raise AppError(404, "project_not_found", "项目不存在")
        result = self.serialize(
            project, updates=self._updates(project_id, limit=20), actor=actor
        )
        now = datetime.now(timezone.utc)
        next_meeting = self.session.scalar(
            select(Meeting)
            .where(
                Meeting.project_id == project_id,
                Meeting.scheduled_start >= now,
                Meeting.status.in_(["draft", "ready", "in_progress"]),
            )
            .order_by(Meeting.scheduled_start, Meeting.id)
            .limit(1)
        )
        recent_decisions = list(
            self.session.scalars(
                select(Decision)
                .where(Decision.project_id == project_id)
                .options(selectinload(Decision.reviewers))
                .order_by(Decision.updated_at.desc(), Decision.id)
                .limit(10)
            )
        )
        series = list(
            self.session.scalars(
                select(MeetingSeries)
                .where(MeetingSeries.project_id == project_id)
                .order_by(MeetingSeries.title, MeetingSeries.id)
            )
        )
        attachments = list(
            self.session.scalars(
                select(Attachment)
                .where(
                    Attachment.target_type == "project",
                    Attachment.target_id == project_id,
                )
                .options(joinedload(Attachment.creator))
                .order_by(Attachment.created_at.desc(), Attachment.id.desc())
            )
        )
        counts = self.session.execute(
            select(
                select(func.count(Meeting.id))
                .where(Meeting.project_id == project_id)
                .scalar_subquery()
                .label("meeting_count"),
                select(func.count(Decision.id))
                .where(Decision.project_id == project_id)
                .scalar_subquery()
                .label("decision_count"),
                select(func.count(ActionItem.id))
                .where(
                    ActionItem.project_id == project_id,
                    ActionItem.status.in_(["open", "in_progress"]),
                )
                .scalar_subquery()
                .label("open_action_count"),
            )
        ).one()
        result.update(
            {
                "next_meeting": (
                    {
                        "id": next_meeting.id,
                        "title": next_meeting.title,
                        "scheduled_start": next_meeting.scheduled_start,
                        "status": next_meeting.status,
                    }
                    if next_meeting is not None
                    else None
                ),
                "recent_decisions": [
                    OutcomeService.serialize(item) for item in recent_decisions
                ],
                "meeting_count": counts.meeting_count,
                "decision_count": counts.decision_count,
                "open_action_count": counts.open_action_count,
                "series_summaries": [
                    {
                        "id": item.id,
                        "title": item.title,
                        "status": item.status,
                        "recurrence_description": item.recurrence_description,
                    }
                    for item in series
                ],
                "attachments": [
                    {
                        "id": item.id,
                        "target_type": item.target_type,
                        "target_id": item.target_id,
                        "original_name": item.original_name,
                        "mime_type": item.mime_type,
                        "size": item.size,
                        "attachment_type": item.attachment_type,
                        "created_by": user_ref(item.creator),
                        "created_at": item.created_at,
                        "download_url": f"/api/attachments/project/{project_id}/{item.id}",
                    }
                    for item in attachments
                ],
            }
        )
        return result

    def list_updates(
        self, project_id: str, actor: User, *, limit: int = 50, offset: int = 0
    ) -> list[dict[str, Any]]:
        WorkspaceAccess(self.session).require_project_view(project_id, actor)
        return [
            self.serialize_update(update)
            for update in self._updates(project_id, limit=limit, offset=offset)
        ]
