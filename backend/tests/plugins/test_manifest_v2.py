from fastapi.testclient import TestClient

from app.main import create_app


def test_v1_manifest_still_loads_with_empty_capabilities(plugin_factory, settings):
    plugin_factory(
        "legacy-ai",
        manifest={
            "id": "legacy-ai",
            "name": "Legacy AI",
            "version": "0.1.0",
            "api_version": 1,
            "backend_entry": "backend.py",
        },
        backend="def register(registry): pass",
        enabled=True,
    )

    app = create_app(settings)
    with TestClient(app):
        descriptor = app.state.plugin_manager.descriptor("legacy-ai")
        assert descriptor is not None
        assert descriptor.manifest.api_version == 1
        assert descriptor.manifest.capabilities.model_dump() == {
            "actions": [],
            "exporters": [],
            "event_subscriptions": [],
            "ui_slots": [],
            "context_scopes": [],
            "external_network": False,
        }


def test_v2_manifest_rejects_unknown_capability(plugin_factory, settings):
    plugin_factory(
        "bad-v2",
        manifest={
            "id": "bad-v2",
            "name": "Bad v2",
            "version": "0.1.0",
            "api_version": 2,
            "backend_entry": "backend.py",
            "capabilities": {"unknown": ["x"]},
        },
        backend="def register(registry): pass",
        enabled=True,
    )

    app = create_app(settings)
    with TestClient(app):
        assert app.state.plugin_manager.descriptor("bad-v2") is None
        assert any(error.plugin_id == "bad-v2" for error in app.state.plugin_manager.errors())
