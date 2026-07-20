from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload, selectinload
from sqlalchemy.orm.exc import StaleDataError

from app.auth.models import User, UserRole, UserStatus
from app.domain.versioning import require_version
from app.errors import AppError
from app.meetings.models import Meeting
from app.projects.models import Project, ProjectMember, ProjectUpdate
from app.projects.schemas import ProjectEdit, ProjectUpdateWrite, ProjectWrite


def user_ref(user: User | None) -> dict[str, str] | None:
    if user is None:
        return None
    return {
        "id": user.id,
        "username": user.username,
        "display_name": user.display_name,
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
            payload.lead_user_id, payload.member_ids
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
            self.session.commit()
        except IntegrityError as exc:
            self.session.rollback()
            raise AppError(
                409,
                "project_slug_conflict",
                "项目标识已存在",
                details={"slug": payload.slug},
            ) from exc
        self.session.refresh(project)
        return project

    def update(
        self, project_id: str, payload: ProjectEdit, actor: User
    ) -> Project:
        self._require_active(actor)
        project = self.require(project_id)
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
                "project_slug_conflict",
                "项目标识已存在",
                details={"slug": changes.get("slug", project.slug)},
            ) from exc
        self.session.refresh(project)
        return project

    def _can_post_update(self, project: Project, actor: User) -> bool:
        if actor.role == UserRole.ADMIN:
            return True
        return any(item.user_id == actor.id for item in project.memberships)

    def create_update(
        self,
        project_id: str,
        payload: ProjectUpdateWrite,
        actor: User,
    ) -> ProjectUpdate:
        self._require_active(actor)
        project = self.require(project_id)
        if not self._can_post_update(project, actor):
            raise AppError(
                403,
                "project_membership_required",
                "只有项目成员可以发布进展",
            )
        update = ProjectUpdate(
            project_id=project.id,
            author_id=actor.id,
            **payload.model_dump(),
        )
        self.session.add(update)
        self.session.commit()
        self.session.refresh(update)
        return update

    def edit_update(
        self,
        update_id: str,
        payload: ProjectUpdateWrite,
        actor: User,
    ) -> ProjectUpdate:
        self._require_active(actor)
        update = self.require_update(update_id)
        if update.author_id != actor.id and actor.role != UserRole.ADMIN:
            raise AppError(
                403,
                "project_update_forbidden",
                "只能修改自己发布的项目进展",
            )
        for field, value in payload.model_dump().items():
            setattr(update, field, value)
        self.session.commit()
        self.session.refresh(update)
        return update

    def delete(self, project_id: str, actor: User) -> None:
        self._require_active(actor)
        project = self.require(project_id)
        if actor.role != UserRole.ADMIN and project.lead_user_id != actor.id:
            raise AppError(
                403,
                "project_delete_forbidden",
                "只有管理员或项目负责人可以删除项目",
            )
        has_meeting = self.session.scalar(
            select(Meeting.id).where(Meeting.project == project.name).limit(1)
        )
        if has_meeting:
            raise AppError(
                409,
                "project_not_empty",
                "项目下已有会议，不能删除",
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
            "author": user_ref(update.author),
            "created_at": update.created_at,
            "updated_at": update.updated_at,
        }

    def _updates(
        self, project_id: str, *, limit: int, offset: int = 0
    ) -> list[ProjectUpdate]:
        statement = (
            select(ProjectUpdate)
            .where(ProjectUpdate.project_id == project_id)
            .options(joinedload(ProjectUpdate.author))
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
    ) -> dict[str, Any]:
        if updates is None:
            updates = self._updates(project.id, limit=20)
        return {
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

    def list(self) -> list[dict[str, Any]]:
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
        projects = self.session.scalars(statement)
        return [self.serialize(project, updates=[]) for project in projects]

    def detail(self, project_id: str) -> dict[str, Any]:
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
        return self.serialize(
            project, updates=self._updates(project_id, limit=20)
        )

    def list_updates(
        self, project_id: str, *, limit: int = 50, offset: int = 0
    ) -> list[dict[str, Any]]:
        self.require(project_id)
        return [
            self.serialize_update(update)
            for update in self._updates(project_id, limit=limit, offset=offset)
        ]
