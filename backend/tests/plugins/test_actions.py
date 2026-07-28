import asyncio
import importlib.util
import logging
from pathlib import Path

import pytest


@pytest.fixture
def ai_work_assistant_backend():
    entry = (
        Path(__file__).resolve().parents[3]
        / "plugins"
        / "ai-work-assistant"
        / "backend.py"
    )
    spec = importlib.util.spec_from_file_location("ai_work_assistant_backend", entry)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_ai_work_assistant_sends_current_editor_text_with_server_snapshot(
    ai_work_assistant_backend, monkeypatch
):
    captured: dict = {}

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"choices": [{"message": {"content": "# AI 草稿"}}]}

    class Client:
        def __init__(self, **_kwargs):
            pass

        async def post(self, _url, **kwargs):
            captured.update(kwargs)
            return Response()

    monkeypatch.setattr(ai_work_assistant_backend.httpx, "AsyncClient", Client)

    result = asyncio.run(
        ai_work_assistant_backend.meeting_summary(
            {"title": "服务端会议快照"},
            {"current_markdown": "## 用户原稿"},
            {
                "base_url": "https://example.test/v1",
                "api_key": "test-key",
                "model": "test-model",
                "timeout_seconds": 10,
            },
        )
    )

    content = captured["json"]["messages"][1]["content"]
    assert "当前编辑栏已有内容；它是待改写的用户草稿" in content
    assert "不得只原样复述当前编辑内容" in content
    assert "资料不足时，只能改写和组织表达，不得编造事实" in content
    assert "当前编辑内容：\n## 用户原稿" in content
    assert "资料：{'title': '服务端会议快照'}" in content
    assert result == {"markdown": "# AI 草稿", "model": "test-model"}


def test_action_suggestions_return_editable_markdown(
    ai_work_assistant_backend, monkeypatch
):
    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "choices": [
                    {
                        "message": {
                            "content": "- 明确负责人并补充截止日期"
                        }
                    }
                ]
            }

    class Client:
        def __init__(self, **_kwargs):
            pass

        async def post(self, _url, **_kwargs):
            return Response()

    monkeypatch.setattr(ai_work_assistant_backend.httpx, "AsyncClient", Client)

    result = asyncio.run(
        ai_work_assistant_backend.action_suggestions(
            {"title": "行动项讨论"},
            {"current_markdown": "原有行动内容"},
            {
                "base_url": "https://example.test/v1",
                "api_key": "test-key",
                "model": "test-model",
                "timeout_seconds": 10,
            },
        )
    )

    assert result == {
        "markdown": "- 明确负责人并补充截止日期",
        "model": "test-model",
    }


@pytest.mark.parametrize(
    ("generator_name", "expected_markdown"),
    [
        ("decision_suggestions", "采用灰度发布，并在一周后复盘效果。"),
        ("open_question_suggestions", "- 如何确认灰度发布的覆盖范围？"),
    ],
)
def test_outcome_suggestions_return_editable_markdown(
    ai_work_assistant_backend, monkeypatch, generator_name, expected_markdown
):
    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"choices": [{"message": {"content": expected_markdown}}]}

    class Client:
        def __init__(self, **_kwargs):
            pass

        async def post(self, _url, **_kwargs):
            return Response()

    monkeypatch.setattr(ai_work_assistant_backend.httpx, "AsyncClient", Client)

    result = asyncio.run(
        getattr(ai_work_assistant_backend, generator_name)(
            {"title": "结果讨论"},
            {"current_markdown": "原有内容"},
            {
                "base_url": "https://example.test/v1",
                "api_key": "test-key",
                "model": "test-model",
                "timeout_seconds": 10,
            },
        )
    )

    assert result == {"markdown": expected_markdown, "model": "test-model"}


def test_ai_work_assistant_declares_bounded_editor_input(ai_work_assistant_backend):
    class Registry:
        def __init__(self):
            self.actions = []

        def register_meeting_action(self, action):
            self.actions.append(action)

    registry = Registry()
    ai_work_assistant_backend.register(registry)

    for action in registry.actions:
        assert action.input_schema == {
            "type": "object",
            "properties": {
                "current_markdown": {"type": "string", "maxLength": 100_000}
            },
            "additionalProperties": False,
        }


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
    assert meeting["summary_markdown"] == ""


def test_action_requires_declared_plugin_configuration(
    plugin_client, plugin_meeting_id
):
    response = plugin_client.post(
        f"/api/meetings/{plugin_meeting_id}/plugin-actions/test-ai.summarize",
        json={},
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "plugin_not_configured"


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
    assert (
        plugin_client.post(
            f"/api/meetings/{plugin_meeting_id}/plugin-actions/test-ai.summarize",
            json={},
        ).status_code
        == 403
    )


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
