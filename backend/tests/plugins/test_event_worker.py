import asyncio

import app.models  # noqa: F401 - register all ORM models
from sqlalchemy import select

from app.database import Database
from app.meetings.models import utcnow
from app.plugins.models import PluginEvent, PluginEventStatus
from app.plugins.worker import PluginJobWorker


class FakeManager:
    def __init__(self, *, failures=0):
        self.failures = failures
        self.calls = 0

    async def invoke_event(self, _event_type, _payload, _session):
        self.calls += 1
        if self.calls <= self.failures:
            raise RuntimeError("provider api_key=secret-value failed")


def event_database():
    database = Database("sqlite://")
    database.create_schema()
    return database


def add_event(database, *, event_id="event-1"):
    with database.session() as session:
        event = PluginEvent(
            event_id=event_id,
            event_type="meeting.completed",
            payload_version=1,
            target_type="meeting",
            target_id="meeting-1",
            payload_json={"meeting_id": "meeting-1"},
            status=PluginEventStatus.queued,
            attempts=0,
            next_attempt_at=utcnow(),
        )
        session.add(event)
        session.commit()


def test_event_worker_marks_successful_event_once():
    database = event_database()
    add_event(database)
    manager = FakeManager()
    worker = PluginJobWorker(database, manager)

    assert asyncio.run(worker.run_event_once()) is True

    with database.session() as session:
        event = session.scalar(select(PluginEvent).where(PluginEvent.event_id == "event-1"))
        assert event.status == PluginEventStatus.succeeded
        assert event.attempts == 1
    assert manager.calls == 1


def test_event_worker_retries_then_dead_letters_with_redacted_error():
    database = event_database()
    add_event(database)
    manager = FakeManager(failures=5)
    worker = PluginJobWorker(database, manager)

    for _ in range(worker.max_event_attempts):
        with database.session() as session:
            session.scalar(select(PluginEvent)).next_attempt_at = utcnow()
            session.commit()
        assert asyncio.run(worker.run_event_once()) is True

    with database.session() as session:
        event = session.scalar(select(PluginEvent))
        assert event.status == PluginEventStatus.failed
        assert event.attempts == worker.max_event_attempts
        assert "secret-value" not in event.last_error
        assert event.finished_at is not None


def test_recover_requeues_processing_events_without_touching_succeeded():
    database = event_database()
    add_event(database, event_id="processing")
    add_event(database, event_id="succeeded")
    with database.session() as session:
        processing = session.get(PluginEvent, "processing")
        processing.status = PluginEventStatus.processing
        succeeded = session.get(PluginEvent, "succeeded")
        succeeded.status = PluginEventStatus.succeeded
        session.commit()

    PluginJobWorker(database, FakeManager()).recover()

    with database.session() as session:
        assert session.get(PluginEvent, "processing").status == PluginEventStatus.queued
        assert session.get(PluginEvent, "succeeded").status == PluginEventStatus.succeeded
