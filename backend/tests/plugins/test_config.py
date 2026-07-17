from sqlalchemy import select

from app.plugins.models import PluginConfig, PluginState


def test_admin_lists_discovered_plugin(plugin_client):
    response = plugin_client.get("/api/admin/plugins")

    assert response.status_code == 200
    plugin = response.json()["plugins"][0]
    assert plugin["id"] == "test-ai"
    assert plugin["enabled"] is True
    assert plugin["config_schema"]["secrets"][0]["key"] == "api_key"


def test_admin_sets_secret_but_never_reads_plaintext(plugin_client):
    response = plugin_client.put(
        "/api/admin/plugins/test-ai/config",
        json={"api_key": "secret-value", "model": "test-model"},
    )

    assert response.status_code == 200
    assert response.json()["api_key"] == {"configured": True}
    assert response.json()["model"] == "test-model"
    assert "secret-value" not in str(response.json())
    with plugin_client.app.state.database.session() as session:
        row = session.scalar(
            select(PluginConfig).where(
                PluginConfig.plugin_id == "test-ai",
                PluginConfig.config_key == "api_key",
            )
        )
        assert row is not None
        assert row.stored_value != "secret-value"


def test_enabled_state_is_persisted_for_next_restart(plugin_client):
    response = plugin_client.put(
        "/api/admin/plugins/test-ai/enabled", json={"enabled": False}
    )

    assert response.status_code == 200
    assert response.json() == {"enabled": False, "restart_required": True}
    with plugin_client.app.state.database.session() as session:
        assert session.get(PluginState, "test-ai").enabled is False


def test_member_cannot_read_plugin_configuration(plugin_client):
    created = plugin_client.post(
        "/api/admin/users",
        json={
            "username": "member",
            "display_name": "Member",
            "password": "member-password-123",
        },
    )
    assert created.status_code == 201
    plugin_client.post("/api/auth/logout")
    plugin_client.post(
        "/api/auth/login",
        json={"username": "member", "password": "member-password-123"},
    )

    assert plugin_client.get("/api/admin/plugins").status_code == 403
