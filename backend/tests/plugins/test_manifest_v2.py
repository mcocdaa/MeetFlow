import asyncio

import pytest
from fastapi.testclient import TestClient

import app.models  # noqa: F401 - register all ORM models
from app.database import Database
from app.main import create_app
from app.plugins.manager import PluginManager


def load_plugin_manager(settings) -> PluginManager:
    database = Database(settings.database_url)
    database.create_schema()
    return PluginManager(settings.plugins_dir, database, settings.app_secret_key)


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


def test_v2_plugin_with_undeclared_action_is_not_loaded(plugin_factory, settings):
    plugin_factory(
        "undeclared-action",
        manifest={
            "id": "undeclared-action",
            "name": "Undeclared action",
            "version": "0.1.0",
            "api_version": 2,
            "backend_entry": "backend.py",
            "capabilities": {"actions": []},
        },
        backend="""
from app.plugins.contracts import MeetingAction

async def handler(context, payload, config):
    return {}

def register(registry):
    registry.register_meeting_action(MeetingAction(
        action_id="undeclared-action.run",
        label="Run",
        description="",
        admin_only=False,
        input_schema={"type": "object"},
        output_schema={"type": "object"},
        handler=handler,
    ))
""",
        enabled=True,
    )

    manager = load_plugin_manager(settings)
    manager.load_enabled()

    assert manager.loaded_actions() == []
    assert any(error.plugin_id == "undeclared-action" for error in manager.errors())


def test_failed_plugin_registration_does_not_leave_event_handler(
    plugin_factory, settings
):
    plugin_factory(
        "atomic",
        manifest={
            "id": "atomic",
            "name": "Atomic registration",
            "version": "0.1.0",
            "api_version": 2,
            "backend_entry": "backend.py",
            "capabilities": {
                "event_subscriptions": ["meeting.completed"],
                "exporters": [],
            },
        },
        backend="""
async def subscriber(payload, config):
    return None

async def exporter(context, config):
    return None

def register(registry):
    registry.register_event_subscriber("meeting.completed", subscriber)
    registry.register_exporter("atomic.export", exporter)
""",
        enabled=True,
    )

    manager = load_plugin_manager(settings)
    manager.load_enabled()

    assert manager.event_subscribers("meeting.completed") == []
    assert any(error.plugin_id == "atomic" for error in manager.errors())


def test_event_handler_obeys_configured_timeout(plugin_factory, settings):
    plugin_factory(
        "slow",
        manifest={
            "id": "slow",
            "name": "Slow event handler",
            "version": "0.1.0",
            "api_version": 2,
            "backend_entry": "backend.py",
            "capabilities": {"event_subscriptions": ["meeting.completed"]},
        },
        backend="""
import asyncio

async def subscriber(payload, config):
    await asyncio.sleep(0.01)

def register(registry):
    registry.register_event_subscriber("meeting.completed", subscriber)
""",
        enabled=True,
    )

    manager = load_plugin_manager(settings)
    manager.plugin_timeout_seconds = 0.001
    manager.load_enabled()

    with manager.database.session() as session:
        with pytest.raises(TimeoutError):
            asyncio.run(manager.invoke_event("meeting.completed", {}, session))
