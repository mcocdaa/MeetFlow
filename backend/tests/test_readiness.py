from app.plugins.contracts import PluginLoadError


def test_runtime_info_reports_package_version_and_readiness(client):
    meta = client.get("/api/meta")
    assert meta.status_code == 200
    assert meta.json()["version"] == "0.1.1"

    response = client.get("/api/health/ready")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "database": "ok",
        "plugins": "ok",
        "worker": "stopped-in-test",
    }


def test_readiness_reports_plugin_load_failure(client):
    client.app.state.plugin_manager._errors.append(
        PluginLoadError(
            plugin_id="broken-plugin",
            error_type="ManifestError",
            message="插件清单无效",
        )
    )

    response = client.get("/api/health/ready")

    assert response.status_code == 503
    assert response.json() == {
        "status": "not_ready",
        "database": "ok",
        "plugins": "error",
        "worker": "stopped-in-test",
    }
