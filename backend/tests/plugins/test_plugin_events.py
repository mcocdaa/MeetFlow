import pytest
from sqlalchemy import select

import app.models  # noqa: F401 - register all ORM models
from app.database import Database
from app.meetings.models import utcnow
from app.plugins.events import record_plugin_event, retry_plugin_event
from app.plugins.models import PluginEvent, PluginEventStatus


def event_database():
    database = Database("sqlite://")
    database.create_schema()
    return database


def add_event(database, *, event_id="event-1", status=PluginEventStatus.queued):
    with database.session() as session:
        event = PluginEvent(
            event_id=event_id,
            event_type="meeting.completed",
            payload_version=1,
            target_type="meeting",
            target_id="meeting-1",
            payload_json={"meeting_id": "m1"},
            status=status,
            attempts=5 if status == PluginEventStatus.failed else 0,
            next_attempt_at=utcnow(),
            claimed_at=utcnow() if status == PluginEventStatus.failed else None,
            finished_at=utcnow() if status == PluginEventStatus.failed else None,
            last_error="provider timeout" if status == PluginEventStatus.failed else None,
        )
        session.add(event)
        session.commit()


def test_retry_failed_event_requeues_same_event_and_clears_runtime_state():
    database = event_database()
    add_event(database, event_id="evt-retry", status=PluginEventStatus.failed)

    with database.session() as session:
        retried = retry_plugin_event(session, "evt-retry")

        assert retried.event_id == "evt-retry"
        assert retried.payload_json == {"meeting_id": "m1"}
        assert retried.status == PluginEventStatus.queued
        assert retried.attempts == 0
        assert retried.claimed_at is None
        assert retried.finished_at is None
        assert retried.last_error is None
        assert retried.next_attempt_at is not None


def test_retry_plugin_event_rejects_missing_or_non_failed_events():
    database = event_database()
    add_event(database, event_id="queued", status=PluginEventStatus.queued)
    add_event(database, event_id="processing", status=PluginEventStatus.processing)
    add_event(database, event_id="succeeded", status=PluginEventStatus.succeeded)

    with database.session() as session:
        with pytest.raises(KeyError):
            retry_plugin_event(session, "missing")
        for event_id in ("queued", "processing", "succeeded"):
            with pytest.raises(ValueError, match="only failed"):
                retry_plugin_event(session, event_id)

    with database.session() as session:
        assert session.scalar(select(PluginEvent).where(PluginEvent.event_id == "queued")).status == PluginEventStatus.queued
        assert session.scalar(select(PluginEvent).where(PluginEvent.event_id == "processing")).status == PluginEventStatus.processing
        assert session.scalar(select(PluginEvent).where(PluginEvent.event_id == "succeeded")).status == PluginEventStatus.succeeded


def test_admin_retry_endpoint_requeues_failed_event_without_payload(plugin_client):
    database = plugin_client.app.state.database
    add_event(database, event_id="evt-admin", status=PluginEventStatus.failed)

    response = plugin_client.post("/api/admin/plugins/events/evt-admin/retry")

    assert response.status_code == 200
    assert response.json()["event_id"] == "evt-admin"
    assert response.json()["status"] == "queued"
    assert response.json()["attempts"] == 0
    assert "payload_json" not in response.json()


def test_admin_retry_endpoint_rejects_missing_and_non_failed_events(plugin_client):
    database = plugin_client.app.state.database
    add_event(database, event_id="evt-queued", status=PluginEventStatus.queued)

    missing = plugin_client.post("/api/admin/plugins/events/missing/retry")
    non_failed = plugin_client.post("/api/admin/plugins/events/evt-queued/retry")

    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "plugin_event_not_found"
    assert non_failed.status_code == 409
    assert non_failed.json()["error"]["code"] == "plugin_event_not_retryable"


def test_record_event_is_idempotent_and_queued(plugin_client, plugin_meeting_id):
    database = plugin_client.app.state.database
    event_id = f"meeting.completed:meeting:{plugin_meeting_id}:1"
    with database.session() as session:
        first = record_plugin_event(
            session,
            event_type="meeting.completed",
            target_type="meeting",
            target_id=plugin_meeting_id,
            payload={"meeting_id": plugin_meeting_id, "version": 1},
            event_id=event_id,
        )
        second = record_plugin_event(
            session,
            event_type="meeting.completed",
            target_type="meeting",
            target_id=plugin_meeting_id,
            payload={"meeting_id": plugin_meeting_id, "version": 1},
            event_id=event_id,
        )
        session.commit()

        assert first.event_id == second.event_id == event_id
        assert first.status == PluginEventStatus.queued
        assert first.attempts == 0
        assert session.scalar(
            select(PluginEvent).where(PluginEvent.event_id == event_id)
        ) is first


def test_record_event_rejects_non_mapping_or_sensitive_payload(plugin_client):
    with plugin_client.app.state.database.session() as session:
        with pytest.raises(ValueError, match="mapping"):
            record_plugin_event(
                session,
                event_type="test.event",
                target_type="meeting",
                target_id="m1",
                payload=["not", "a", "mapping"],
            )
        with pytest.raises(ValueError, match="sensitive"):
            record_plugin_event(
                session,
                event_type="test.event",
                target_type="meeting",
                target_id="m1",
                payload={"api_key": "do-not-store"},
            )
