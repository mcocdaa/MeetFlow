from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.auth.models import User

if TYPE_CHECKING:
    from app.meetings.service import MeetingService


class MeetingQueries:
    """Read-side boundary; the service methods remain a compatibility facade."""

    def __init__(self, service: MeetingService):
        self.service = service

    def list_series(self, project_id: str) -> list[dict[str, Any]]:
        return self.service._list_series_impl(project_id)

    def list_meetings(self, project_id: str) -> list[dict[str, Any]]:
        return self.service._list_meetings_impl(project_id)

    def series_detail(self, series_id: str) -> dict[str, Any]:
        return self.service._series_detail_impl(series_id)

    def meeting_detail(self, meeting_id: str) -> dict[str, Any]:
        return self.service._meeting_detail_impl(meeting_id)

    def package(self, meeting_id: str) -> dict[str, Any]:
        return self.service._package_impl(meeting_id)

    def plugin_context(self, meeting_id: str, user: User) -> dict[str, Any]:
        return self.service._plugin_context_impl(meeting_id, user)
