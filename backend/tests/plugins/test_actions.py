import logging


def configure_plugin(plugin_client):
    response = plugin_client.put(
        "/api/admin/plugins/test-ai/config",
        json={"api_key": "secret-value", "model": "test-model"},
    )
    assert response.status_code == 200


def test_user_discovers_and_executes_registered_action(
    plugin_client, plugin_meeting_id
):
    configure_plugin(plugin_client)

    actions = plugin_client.get("/api/plugins/actions").json()
    assert actions[0]["action_id"] == "test-ai.summarize"
    result = plugin_client.post(
        f"/api/meetings/{plugin_meeting_id}/plugin-actions/test-ai.summarize",
        json={},
    )

    assert result.status_code == 200
    assert result.json()["markdown"] == "# Draft summary for Plugin meeting"
    assert result.json()["model"] == "test-model"
    meeting = plugin_client.get(f"/api/meetings/{plugin_meeting_id}").json()
    assert meeting["summary_markdown"] == ""


def test_action_requires_declared_plugin_configuration(
    plugin_client, plugin_meeting_id
):
    response = plugin_client.post(
        f"/api/meetings/{plugin_meeting_id}/plugin-actions/test-ai.summarize",
        json={},
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "plugin_not_configured"


def test_admin_only_action_is_hidden_and_forbidden_for_member(
    plugin_client, plugin_meeting_id
):
    configure_plugin(plugin_client)
    action = plugin_client.app.state.plugin_manager.loaded_actions()[0]
    action.admin_only = True
    plugin_client.post(
        "/api/admin/users",
        json={
            "username": "member",
            "display_name": "Member",
            "password": "member-password-123",
        },
    )
    plugin_client.post("/api/auth/logout")
    plugin_client.post(
        "/api/auth/login",
        json={"username": "member", "password": "member-password-123"},
    )

    assert plugin_client.get("/api/plugins/actions").json() == []
    assert (
        plugin_client.post(
            f"/api/meetings/{plugin_meeting_id}/plugin-actions/test-ai.summarize",
            json={},
        ).status_code
        == 403
    )


def test_plugin_failure_log_contains_metadata_not_secret(
    plugin_client, plugin_meeting_id, caplog
):
    configure_plugin(plugin_client)
    action = plugin_client.app.state.plugin_manager.loaded_actions()[0]

    async def failing(_context, _payload, _config):
        raise RuntimeError("secret-value")

    action.handler = failing
    with caplog.at_level(logging.ERROR):
        response = plugin_client.post(
            f"/api/meetings/{plugin_meeting_id}/plugin-actions/test-ai.summarize",
            json={},
        )

    assert response.status_code == 502
    assert "test-ai.summarize" in caplog.text
    assert "secret-value" not in caplog.text
