from __future__ import annotations

from typing import TYPE_CHECKING

from app.auth.models import User
from app.domain.unit_of_work import UnitOfWork
from app.meetings.schemas import LifecycleCommand
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.exc import StaleDataError

if TYPE_CHECKING:
    from app.meetings.models import Meeting
    from app.meetings.service import MeetingService


class MeetingLifecycleCommands:
    """Command boundary for meeting lifecycle actions.

    The service remains the compatibility facade for existing callers. Keeping
    the command object small lets us move persistence details incrementally
    without changing API routes or the plugin context contract.
    """

    def __init__(self, service: MeetingService, uow: UnitOfWork):
        self.service = service
        self.uow = uow

    def start(self, meeting_id: str, payload: LifecycleCommand, actor: User) -> Meeting:
        self.service._require_active(actor)
        try:
            meeting = self.uow.execute(
                lambda _session: self.service._start_impl(
                    meeting_id, payload, actor, commit=False
                )
            )
        except (StaleDataError, IntegrityError) as exc:
            self.service._raise_meeting_stale(meeting_id, payload.expected_version, exc)
        return self.service._reload_meeting(meeting.id)

    def finish(self, meeting_id: str, payload: LifecycleCommand, actor: User) -> Meeting:
        self.service._require_active(actor)
        try:
            meeting = self.uow.execute(
                lambda _session: self.service._finish_impl(
                    meeting_id, payload, actor, commit=False
                )
            )
        except (StaleDataError, IntegrityError) as exc:
            self.service._raise_meeting_stale(meeting_id, payload.expected_version, exc)
        return self.service._reload_meeting(meeting.id)
