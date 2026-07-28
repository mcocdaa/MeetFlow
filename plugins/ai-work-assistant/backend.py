"""OpenAI-compatible editor content generation for MeetFlow.

This plugin deliberately has no MeetFlow write access. Each result is returned
to the active client editor, where the user can edit, undo, and save normally.
"""

from typing import Any

import httpx

from app.plugins.contracts import MeetingAction


def _endpoint(base_url: str) -> str:
    return f"{base_url.rstrip('/')}/chat/completions"


def _editor_context(current_markdown: str) -> str:
    if current_markdown.strip():
        return (
            "当前编辑栏已有内容；生成结果会整体替换该编辑栏。"
            "必须保留其中可证实的具体事实，并在其基础上整理补充；"
            "不得忽略、清空或编造已有内容。"
            f"\n\n当前编辑内容：\n{current_markdown}"
        )
    return "当前编辑栏当前为空；请仅根据资料生成可编辑内容。"


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
                        "你是 MeetFlow 的工作助手。只根据给定资料生成中文内容，"
                        "不要声称执行了未给出的事实。输出 Markdown，不调用工具。"
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"{instruction}\n\n{_editor_context(current_markdown)}"
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
        "根据当前讨论，生成一项可直接填写到“行动内容”中的行动项内容。"
        "只输出可编辑的 Markdown 文本；不要列出检查流程、会议状态或多个候选项。",
        context,
        payload,
        config,
    )


async def decision_suggestions(context, payload, config):
    return await _draft(
        "根据当前讨论，生成一项可直接填写到“决策内容”中的决策内容。"
        "只输出可编辑的 Markdown 文本；不要添加标题、实施计划或多个候选项。",
        context,
        payload,
        config,
    )


async def open_question_suggestions(context, payload, config):
    return await _draft(
        "根据当前讨论，生成一项可直接填写到“开放问题内容”中的问题内容。"
        "只输出可编辑的 Markdown 文本；不要假设问题已经解决。",
        context,
        payload,
        config,
    )


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
            description="基于当前会议资料生成可编辑纪要内容",
            admin_only=False,
            input_schema=editor_input,
            output_schema=common_output,
            handler=meeting_summary,
            target_types=("meeting",),
        )
    )
    registry.register_meeting_action(
        MeetingAction(
            action_id="ai-work-assistant.decision_suggestions",
            label="AI 建议决策",
            description="基于会议资料生成可编辑决策内容",
            admin_only=False,
            input_schema=editor_input,
            output_schema=common_output,
            handler=decision_suggestions,
            target_types=("meeting",),
        )
    )
    registry.register_meeting_action(
        MeetingAction(
            action_id="ai-work-assistant.open_question_suggestions",
            label="AI 梳理开放问题",
            description="基于会议资料生成可编辑开放问题内容",
            admin_only=False,
            input_schema=editor_input,
            output_schema=common_output,
            handler=open_question_suggestions,
            target_types=("meeting",),
        )
    )
    registry.register_meeting_action(
        MeetingAction(
            action_id="ai-work-assistant.project_progress",
            label="总结项目进展",
            description="基于当前项目资料生成可编辑进展内容",
            admin_only=False,
            input_schema=editor_input,
            output_schema=common_output,
            handler=project_progress,
            target_types=("project",),
        )
    )
    registry.register_meeting_action(
        MeetingAction(
            action_id="ai-work-assistant.action_suggestions",
            label="AI 建议行动项",
            description="基于会议资料生成可编辑行动项内容",
            admin_only=False,
            input_schema=editor_input,
            output_schema=common_output,
            handler=action_suggestions,
            target_types=("meeting",),
        )
    )
