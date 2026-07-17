from fastapi.testclient import TestClient

from app.main import create_app


def test_empty_registry_does_not_block_startup(client):
    assert client.get("/api/health").status_code == 200
    assert client.app.state.plugin_manager.loaded_actions() == []
    assert client.app.state.plugin_manager.errors() == []


def test_broken_plugin_is_reported_without_blocking_core(
    plugin_factory, settings
):
    plugin_factory(
        "broken",
        manifest={
            "id": "broken",
            "name": "Broken",
            "version": "0.1.0",
            "api_version": 1,
            "backend_entry": "backend.py",
        },
        backend="raise RuntimeError('broken import')",
        enabled=True,
    )

    app = create_app(settings)
    with TestClient(app) as client:
        assert client.get("/api/health").status_code == 200
        errors = client.app.state.plugin_manager.errors()
        assert len(errors) == 1
        assert errors[0].plugin_id == "broken"
        assert "broken import" not in errors[0].message


def test_manifest_id_must_match_registry_id(plugin_factory, settings):
    plugin_factory(
        "registered-name",
        manifest={
            "id": "different-name",
            "name": "Mismatch",
            "version": "0.1.0",
            "api_version": 1,
            "backend_entry": "backend.py",
        },
        backend="def register(registry): pass",
        enabled=True,
    )

    app = create_app(settings)
    with TestClient(app):
        errors = app.state.plugin_manager.errors()
        assert errors[0].error_type == "ManifestError"
