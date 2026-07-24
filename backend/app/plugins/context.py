"""Bounded, text-only context passed from MeetFlow core to plugins."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.auth.models import User
from app.meetings.service import MeetingService
from app.projects.service import ProjectService


class PluginContextBuilder:
    max_total_characters = 24_000
    max_text_characters = 4_000

    def __init__(self, session: Session):
        self.session = session

    def meeting(self, meeting_id: str, user: User) -> dict[str, Any]:
        return self._bounded(MeetingService(self.session).plugin_context(meeting_id, user))

    def project(self, project_id: str, _user: User) -> dict[str, Any]:
        return self._bounded(ProjectService(self.session).detail(project_id))

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
