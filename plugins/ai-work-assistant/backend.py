"""OpenAI-compatible draft generation for MeetFlow.

This plugin deliberately has no MeetFlow write access.  Each result is a draft
that a user must review and apply through the core application's normal APIs.
"""

from typing import Any

import httpx

from app.plugins.contracts import MeetingAction
from app.meetings.schemas import MeetingEdit
from app.meetings.service import MeetingService
from app.projects.schemas import ProjectUpdateWrite
from app.projects.service import ProjectService


def _endpoint(base_url: str) -> str:
    return f"{base_url.rstrip('/')}/chat/completions"


async def _draft(
    instruction: str,
    context: dict[str, Any],
    payload: dict[str, Any],
    config: dict[str, Any],
) -> dict[str, Any]:
    current_markdown = payload.get("current_markdown", "")
    if not isinstance(current_markdown, str):
        current_markdown = ""
    response = await httpx.AsyncClient(
        timeout=float(config["timeout_seconds"])
    ).post(
        _endpoint(config["base_url"]),
        headers={"Authorization": f"Bearer {config['api_key']}"},
        json={
            "model": config["model"],
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "你是 MeetFlow 的工作助手。只根据给定资料生成中文草稿，"
                        "不要声称执行了未给出的事实。输出 Markdown，不调用工具。"
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"{instruction}\n\n当前编辑内容：{current_markdown}"
                        f"\n\n资料：{context}"
                    ),
                },
            ],
            "temperature": 0.2,
        },
    )
    response.raise_for_status()
    payload = response.json()
    markdown = payload["choices"][0]["message"]["content"].strip()
    return {"markdown": markdown, "model": config["model"]}


async def meeting_summary(context, payload, config):
    return await _draft("整理为会议纪要，包含结论、待确认事项与后续行动。", context, payload, config)


async def project_progress(context, payload, config):
    return await _draft("整理为项目进展摘要，包含进展、风险、下一步。", context, payload, config)


async def action_suggestions(context, payload, config):
    return await _draft(
        "根据当前讨论，生成一项可直接填写到“行动内容”中的行动项草稿。"
        "只输出可编辑的 Markdown 文本；不要列出检查流程、会议状态或多个候选项。",
        context,
        payload,
        config,
    )


def apply_meeting_summary(job, payload, actor, session):
    markdown = payload.get("edited_markdown")
    expected_version = payload.get("expected_version")
    if (
        not isinstance(markdown, str)
        or not markdown.strip()
        or not isinstance(expected_version, int)
    ):
        raise ValueError("meeting summary requires markdown and version")
    meeting = MeetingService(session).update_meeting(
        job.target_id,
        MeetingEdit(expected_version=expected_version, summary_markdown=markdown),
        actor,
    )
    return MeetingService(session).serialize_meeting(meeting)


def apply_project_progress(job, payload, actor, session):
    markdown = payload.get("edited_markdown")
    if not isinstance(markdown, str) or not markdown.strip():
        raise ValueError("project progress requires markdown")
    update = ProjectService(session).create_update(
        job.target_id,
        ProjectUpdateWrite(content_markdown=markdown, source="ai_draft_applied"),
        actor,
    )
    return ProjectService(session).serialize_update(update)


def register(registry):
    common_output = {"type": "object", "required": ["markdown", "model"]}
    editor_input = {
        "type": "object",
        "properties": {
            "current_markdown": {"type": "string", "maxLength": 100_000}
        },
        "additionalProperties": False,
    }
    registry.register_meeting_action(
        MeetingAction(
            action_id="ai-work-assistant.meeting_summary",
            label="生成会议纪要",
            description="基于当前会议资料生成可编辑纪要草稿",
            admin_only=False,
            input_schema=editor_input,
            output_schema=common_output,
            handler=meeting_summary,
            apply_handler=apply_meeting_summary,
            target_types=("meeting",),
        )
    )
    registry.register_meeting_action(
        MeetingAction(
            action_id="ai-work-assistant.project_progress",
            label="总结项目进展",
            description="基于当前项目资料生成可编辑进展草稿",
            admin_only=False,
            input_schema=editor_input,
            output_schema=common_output,
            handler=project_progress,
            apply_handler=apply_project_progress,
            target_types=("project",),
        )
    )
    registry.register_meeting_action(
        MeetingAction(
            action_id="ai-work-assistant.action_suggestions",
            label="AI 建议行动项",
            description="基于会议资料生成可编辑行动项草稿",
            admin_only=False,
            input_schema=editor_input,
            output_schema=common_output,
            handler=action_suggestions,
            target_types=("meeting",),
        )
    )
