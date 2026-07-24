"""OpenAI-compatible draft generation for MeetFlow.

This plugin deliberately has no MeetFlow write access.  Each result is a draft
that a user must review and apply through the core application's normal APIs.
"""

from typing import Any

import httpx

from app.plugins.contracts import MeetingAction


def _endpoint(base_url: str) -> str:
    return f"{base_url.rstrip('/')}/chat/completions"


async def _draft(
    instruction: str,
    context: dict[str, Any],
    _payload: dict[str, Any],
    config: dict[str, Any],
) -> dict[str, Any]:
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
                {"role": "user", "content": f"{instruction}\n\n资料：{context}"},
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
    draft = await _draft("建议可执行的行动项，使用清晰的 Markdown 列表。", context, payload, config)
    return {**draft, "candidates": []}


def register(registry):
    common_output = {"type": "object", "required": ["markdown", "model"]}
    registry.register_meeting_action(MeetingAction(
        action_id="ai-work-assistant.meeting_summary",
        label="生成会议纪要",
        description="基于当前会议资料生成可编辑纪要草稿",
        admin_only=False,
        input_schema={"type": "object"},
        output_schema=common_output,
        handler=meeting_summary,
        target_types=("meeting",),
    ))
    registry.register_meeting_action(MeetingAction(
        action_id="ai-work-assistant.project_progress",
        label="总结项目进展",
        description="基于当前项目资料生成可编辑进展草稿",
        admin_only=False,
        input_schema={"type": "object"},
        output_schema=common_output,
        handler=project_progress,
        target_types=("project",),
    ))
    registry.register_meeting_action(MeetingAction(
        action_id="ai-work-assistant.action_suggestions",
        label="建议行动项",
        description="基于会议资料生成待确认行动项建议",
        admin_only=False,
        input_schema={"type": "object"},
        output_schema={"type": "object", "required": ["markdown", "model", "candidates"]},
        handler=action_suggestions,
        target_types=("meeting",),
    ))
