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
    assert meeting["conclusions_markdown"] == ""


def test_invalid_action_payload_is_rejected(plugin_client, plugin_meeting_id):
    configure_plugin(plugin_client)

    response = plugin_client.post(
        f"/api/meetings/{plugin_meeting_id}/plugin-actions/test-ai.summarize",
        json=[],
    )

    assert response.status_code == 422
