from pathlib import Path

from fastapi.testclient import TestClient
import yaml

from app.main import create_app


def test_ai_work_assistant_declares_three_scoped_actions(settings):
    settings.plugins_dir = (
        Path(__file__).resolve().parents[3] / "plugins"
    )
    app = create_app(settings)

    with TestClient(app):
        actions = {
            action.action_id: action
            for action in app.state.plugin_manager.loaded_actions()
        }
        assert set(actions) == {
            "ai-work-assistant.meeting_summary",
            "ai-work-assistant.project_progress",
            "ai-work-assistant.action_suggestions",
        }
        assert actions["ai-work-assistant.meeting_summary"].target_types == (
            "meeting",
        )
        assert actions["ai-work-assistant.project_progress"].target_types == (
            "project",
        )


def test_broken_plugin_is_reported_without_blocking_core(plugin_factory, settings):
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


def test_registry_path_cannot_escape_plugin_root(settings):
    settings.plugins_dir.mkdir(parents=True, exist_ok=True)
    outside = settings.plugins_dir.parent / "outside-plugin"
    outside.mkdir()
    (outside / "plugin.yaml").write_text(
        yaml.safe_dump(
            {
                "id": "escape",
                "name": "Escape",
                "version": "0.1.0",
                "api_version": 1,
                "backend_entry": "backend.py",
            }
        ),
        encoding="utf-8",
    )
    (outside / "backend.py").write_text(
        "def register(registry): pass", encoding="utf-8"
    )
    (settings.plugins_dir / "plugins.yaml").write_text(
        yaml.safe_dump(
            {"plugins": {"escape": {"path": "../outside-plugin", "enabled": True}}}
        ),
        encoding="utf-8",
    )

    app = create_app(settings)
    with TestClient(app):
        assert app.state.plugin_manager.loaded_actions() == []
        assert app.state.plugin_manager.errors()[0].error_type == "ManifestError"
