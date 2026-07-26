from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        app_env="test",
        database_url=f"sqlite:///{tmp_path / 'test.db'}",
        data_dir=tmp_path / "data",
        plugins_dir=tmp_path / "plugins",
        admin_username="admin",
        admin_password="correct-horse-battery",
        app_secret_key="test-secret-key-with-at-least-32-chars",
        allow_registration=True,
        secure_cookies=False,
    )


@pytest.fixture
def client(settings: Settings):
    app = create_app(settings)
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def authenticated_client(client):
    response = client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "correct-horse-battery"},
    )
    assert response.status_code == 200
    return client


@pytest.fixture
def meeting_id(authenticated_client):
    user = authenticated_client.get("/api/auth/me").json()
    project = authenticated_client.post(
        "/api/projects",
        json={
            "name": "Fixture project",
            "slug": "fixture-project",
            "status": "active",
            "lead_user_id": user["id"],
            "member_ids": [user["id"]],
        },
    ).json()
    response = authenticated_client.post(
        f"/api/projects/{project['id']}/meetings",
        json={
            "title": "Fixture meeting",
            "scheduled_start": "2026-07-17T13:30:00Z",
            "scheduled_end": "2026-07-17T14:30:00Z",
            "participants": [{"user_id": user["id"], "participation_role": "host"}],
            "raw_notes_markdown": "Fixture notes",
            "summary_markdown": "Fixture conclusion",
        },
    )
    assert response.status_code == 201
    return response.json()["id"]


@pytest.fixture
def plugin_factory(settings):
    registry = {"plugins": {}}
    settings.plugins_dir.mkdir(parents=True, exist_ok=True)

    def create(
        plugin_id: str,
        manifest: dict,
        backend: str,
        enabled: bool,
    ) -> Path:
        plugin_dir = settings.plugins_dir / plugin_id
        plugin_dir.mkdir(parents=True, exist_ok=True)
        (plugin_dir / "plugin.yaml").write_text(
            yaml.safe_dump(manifest), encoding="utf-8"
        )
        (plugin_dir / manifest["backend_entry"]).write_text(backend, encoding="utf-8")
        registry["plugins"][plugin_id] = {
            "path": plugin_id,
            "enabled": enabled,
        }
        (settings.plugins_dir / "plugins.yaml").write_text(
            yaml.safe_dump(registry), encoding="utf-8"
        )
        return plugin_dir

    return create


@pytest.fixture
def plugin_client(settings, plugin_factory):
    plugin_factory(
        "test-ai",
        manifest={
            "id": "test-ai",
            "name": "Test AI",
            "version": "0.1.0",
            "api_version": 1,
            "backend_entry": "backend.py",
            "config_schema": {
                "fields": [{"key": "model", "type": "string", "required": True}],
                "secrets": [{"key": "api_key", "type": "secret", "required": True}],
            },
        },
        backend="""
from app.plugins.contracts import MeetingAction

async def summarize(context, payload, config):
    return {
        "markdown": f"# Draft summary for {context['title']}",
        "suggested_patch": {"conclusions_markdown": "Draft conclusion"},
        "model": config["model"],
    }

def register(registry):
    registry.register_meeting_action(MeetingAction(
        action_id="test-ai.summarize",
        label="生成会议纪要",
        description="生成测试纪要草稿",
        admin_only=False,
        input_schema={"type": "object"},
        output_schema={
            "type": "object",
            "required": ["markdown", "suggested_patch", "model"],
        },
        handler=summarize,
    ))
""",
        enabled=True,
    )
    app = create_app(settings)
    with TestClient(app) as test_client:
        login = test_client.post(
            "/api/auth/login",
            json={
                "username": "admin",
                "password": "correct-horse-battery",
            },
        )
        assert login.status_code == 200
        yield test_client


@pytest.fixture
def ai_plugin_client(settings, plugin_factory):
    plugin_root = (
        Path(__file__).resolve().parents[2] / "plugins" / "ai-work-assistant"
    )
    plugin_factory(
        "ai-work-assistant",
        manifest=yaml.safe_load(
            (plugin_root / "plugin.yaml").read_text(encoding="utf-8")
        ),
        backend=(plugin_root / "backend.py").read_text(encoding="utf-8"),
        enabled=True,
    )
    app = create_app(settings)
    with TestClient(app) as test_client:
        login = test_client.post(
            "/api/auth/login",
            json={
                "username": "admin",
                "password": "correct-horse-battery",
            },
        )
        assert login.status_code == 200
        yield test_client


def create_plugin_meeting(test_client: TestClient) -> str:
    user = test_client.get("/api/auth/me").json()
    project = test_client.post(
        "/api/projects",
        json={
            "name": "Plugin project",
            "slug": "plugin-project",
            "status": "active",
            "lead_user_id": user["id"],
            "member_ids": [user["id"]],
        },
    ).json()
    response = test_client.post(
        f"/api/projects/{project['id']}/meetings",
        json={
            "title": "Plugin meeting",
            "scheduled_start": "2026-07-17T13:30:00Z",
            "scheduled_end": "2026-07-17T14:30:00Z",
            "participants": [{"user_id": user["id"], "participation_role": "host"}],
            "raw_notes_markdown": "Summarize this",
            "summary_markdown": "",
        },
    )
    assert response.status_code == 201
    return response.json()["id"]


@pytest.fixture
def plugin_meeting_id(plugin_client):
    return create_plugin_meeting(plugin_client)


@pytest.fixture
def ai_plugin_meeting_id(ai_plugin_client):
    return create_plugin_meeting(ai_plugin_client)
