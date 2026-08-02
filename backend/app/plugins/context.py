"""Bounded, text-only context passed from MeetFlow core to plugins."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import exists, or_, select
from sqlalchemy.orm import Session

from app.agendas.models import AgendaItem
from app.attention.service import AttentionService
from app.auth.models import User
from app.errors import AppError
from app.meetings.service import MeetingService
from app.projects.models import Project, ProjectMember, ProjectUpdate
from app.projects.access import WorkspaceAccess
from app.projects.service import ProjectService


class PluginContextBuilder:
    max_total_characters = 24_000
    max_text_characters = 4_000

    def __init__(self, session: Session):
        self.session = session

    def meeting(self, meeting_id: str, user: User) -> dict[str, Any]:
        WorkspaceAccess(self.session).require_meeting_view(meeting_id, user)
        return self._bounded(MeetingService(self.session).plugin_context(meeting_id, user))

    def agenda_item(self, agenda_item_id: str, user: User) -> dict[str, Any]:
        agenda_item = self.session.get(AgendaItem, agenda_item_id)
        if agenda_item is None:
            raise AppError(404, "agenda_item_not_found", "议题不存在")
        WorkspaceAccess(self.session).require_meeting_view(
            agenda_item.meeting_id, user
        )
        meeting_context = MeetingService(self.session).plugin_context(
            agenda_item.meeting_id, user
        )
        current_agenda_item = next(
            item
            for item in meeting_context["agenda_items"]
            if item["id"] == agenda_item.id
        )
        return self._bounded(
            {
                "current_agenda_item": current_agenda_item,
                **meeting_context,
            }
        )

    def project(self, project_id: str, user: User) -> dict[str, Any]:
        return self._bounded(ProjectService(self.session).detail(project_id, user))

    def user_work_brief(self, user: User) -> dict[str, Any]:
        member_of_project = exists(
            select(ProjectMember.project_id).where(
                ProjectMember.project_id == Project.id,
                ProjectMember.user_id == user.id,
            )
        )
        latest_update_id = (
            select(ProjectUpdate.id)
            .where(ProjectUpdate.project_id == Project.id)
            .order_by(ProjectUpdate.created_at.desc(), ProjectUpdate.id.desc())
            .limit(1)
            .correlate(Project)
            .scalar_subquery()
        )
        rows = self.session.execute(
            select(Project, ProjectUpdate)
            .outerjoin(ProjectUpdate, ProjectUpdate.id == latest_update_id)
            .where(
                or_(Project.lead_user_id == user.id, member_of_project)
            )
            .order_by(Project.updated_at.desc(), Project.id)
            .limit(60)
        ).all()
        projects = [
            {
                "id": project.id,
                "name": project.name,
                "summary": project.summary,
                "status": project.status,
                "health": project.health,
                "target_date": project.target_date,
                "updated_at": project.updated_at,
                "latest_update": update.content_markdown if update else "",
            }
            for project, update in rows
        ]
        return self._bounded(
            {
                "projects": projects,
                "attention": AttentionService(self.session).for_user(user),
            }
        )

    def _bounded(self, value: Any) -> dict[str, Any]:
        budget = [self.max_total_characters]
        bounded = self._clip(value, budget)
        if not isinstance(bounded, dict):
            raise TypeError("plugin context must be a mapping")
        if budget[0] == 0:
            bounded["truncated"] = True
        return bounded

    def _clip(self, value: Any, budget: list[int]) -> Any:
        if isinstance(value, str):
            allowed = min(len(value), self.max_text_characters, budget[0])
            budget[0] -= allowed
            return value[:allowed]
        if isinstance(value, (date, datetime)):
            return value.isoformat()
        if isinstance(value, list):
            result = []
            for item in value:
                if budget[0] == 0:
                    break
                result.append(self._clip(item, budget))
            return result
        if isinstance(value, dict):
            return {
                str(key): self._clip(item, budget)
                for key, item in value.items()
                if budget[0] > 0 or not isinstance(item, str)
            }
        return value
