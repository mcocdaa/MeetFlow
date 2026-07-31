import pytest
from sqlalchemy import select

from app.plugins.events import record_plugin_event
from app.plugins.models import PluginEvent, PluginEventStatus


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
