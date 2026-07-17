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


def test_action_requires_declared_plugin_configuration(
    plugin_client, plugin_meeting_id
):
    response = plugin_client.post(
        f"/api/meetings/{plugin_meeting_id}/plugin-actions/test-ai.summarize",
        json={},
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "plugin_not_configured"


def test_manifest_rescan_does_not_change_loaded_action_contract(
    plugin_client, plugin_meeting_id
):
    configure_plugin(plugin_client)
    manifest_path = (
        plugin_client.app.state.settings.plugins_dir
        / "test-ai"
        / "plugin.yaml"
    )
    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    manifest["config_schema"] = {
        "fields": [{"key": "replacement", "type": "string", "required": True}],
        "secrets": [],
    }
    manifest_path.write_text(yaml.safe_dump(manifest), encoding="utf-8")

    assert plugin_client.get("/api/admin/plugins").status_code == 200
    response = plugin_client.post(
        f"/api/meetings/{plugin_meeting_id}/plugin-actions/test-ai.summarize",
        json={},
    )

    assert response.status_code == 200
    assert response.json()["model"] == "test-model"


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
    assert plugin_client.post(
        f"/api/meetings/{plugin_meeting_id}/plugin-actions/test-ai.summarize",
        json={},
    ).status_code == 403


def test_invalid_plugin_output_is_isolated(plugin_client, plugin_meeting_id):
    configure_plugin(plugin_client)
    action = plugin_client.app.state.plugin_manager.loaded_actions()[0]

    async def invalid_output(_context, _payload, _config):
        return {"markdown": "missing required fields"}

    action.handler = invalid_output
    response = plugin_client.post(
        f"/api/meetings/{plugin_meeting_id}/plugin-actions/test-ai.summarize",
        json={},
    )

    assert response.status_code == 502
    assert response.json()["error"]["code"] == "plugin_invalid_output"


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


def test_cooperative_plugin_timeout_is_enforced(plugin_client, plugin_meeting_id):
    configure_plugin(plugin_client)
    plugin_client.app.state.settings.plugin_timeout_seconds = 0.001
    action = plugin_client.app.state.plugin_manager.loaded_actions()[0]

    async def slow(_context, _payload, _config):
        await asyncio.sleep(0.05)
        return {
            "markdown": "late",
            "suggested_patch": {},
            "model": "test-model",
        }

    action.handler = slow
    response = plugin_client.post(
        f"/api/meetings/{plugin_meeting_id}/plugin-actions/test-ai.summarize",
        json={},
    )

    assert response.status_code == 504
import asyncio
import logging

import yaml
