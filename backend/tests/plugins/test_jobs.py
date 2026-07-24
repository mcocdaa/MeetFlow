from app.plugins.jobs import PluginJobService


def test_same_active_action_returns_existing_job(
    plugin_client, plugin_meeting_id
):
    manager = plugin_client.app.state.plugin_manager
    database = plugin_client.app.state.database
    actor = plugin_client.get("/api/auth/me").json()

    with database.session() as session:
        service = PluginJobService(session, manager)
        first, created = service.submit(
            "test-ai.summarize", "meeting", plugin_meeting_id, {}, actor["id"]
        )
        second, duplicate = service.submit(
            "test-ai.summarize", "meeting", plugin_meeting_id, {}, actor["id"]
        )

    assert created is True
    assert duplicate is False
    assert second.id == first.id
