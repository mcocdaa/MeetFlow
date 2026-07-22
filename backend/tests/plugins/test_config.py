from sqlalchemy import select

from app.plugins.models import PluginConfig


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


def test_saving_config_removes_obsolete_database_keys(plugin_client):
    manager = plugin_client.app.state.plugin_manager
    actor_id = plugin_client.get("/api/auth/me").json()["id"]
    with plugin_client.app.state.database.session() as session:
        session.add(
            PluginConfig(
                plugin_id="test-ai",
                config_key="obsolete_secret",
                stored_value=manager.secret_box.encrypt('"must-be-deleted"'),
                is_secret=True,
                updated_by=actor_id,
            )
        )
        session.commit()

    plugin_client.put(
        "/api/admin/plugins/test-ai/config",
        json={"api_key": "secret-value", "model": "test-model"},
    )

    with plugin_client.app.state.database.session() as session:
        obsolete = session.scalar(
            select(PluginConfig).where(
                PluginConfig.plugin_id == "test-ai",
                PluginConfig.config_key == "obsolete_secret",
            )
        )
        assert obsolete is None
