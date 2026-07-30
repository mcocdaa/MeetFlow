from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from app.database import Database
from app.meetings.service import MeetingService


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class MeetingSeriesScheduler:
    """Low-frequency in-process materializer for active series rules."""

    def __init__(self, database: Database):
        self.database = database
        self._stop = asyncio.Event()

    def run_once(self, *, now: datetime | None = None) -> list[str]:
        with self.database.session() as session:
            meetings = MeetingService(session).materialize_due_occurrences(
                now=now or utcnow()
            )
            return [meeting.id for meeting in meetings]

    async def serve(self) -> None:
        while not self._stop.is_set():
            self.run_once()
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=60)
            except TimeoutError:
                pass

    def stop(self) -> None:
        self._stop.set()
