"""OpenAI-compatible editor content generation for MeetFlow.

This plugin deliberately has no MeetFlow write access. Each result is returned
to the active client editor, where the user can edit, undo, and save normally.
"""

import json
from collections.abc import AsyncIterator
from typing import Any

import httpx

from app.plugins.contracts import MeetingAction


def _endpoint(base_url: str) -> str:
    return f"{base_url.rstrip('/')}/chat/completions"


def _editor_context(current_markdown: str) -> str:
    if current_markdown.strip():
        return (
            "当前编辑栏已有内容；它是待改写的用户草稿，生成结果会整体替换该编辑栏。"
            "必须输出经过改写或补充、可直接使用的完整文本；不得只原样复述当前编辑内容。"
            "保留其中可证实的具体事实，并结合资料补充；"
            "资料不足时，只能改写和组织表达，不得编造事实。"
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


async def agenda_notes(context, payload, config):
    return await _draft(
        "只整理当前议题（current_agenda_item）的记录；可参考同一会议上下文核验，"
        "不得整理、汇总或合并其他议题的记录。"
        "输出可整体替换当前议题记录的完整、可编辑 Markdown。"
        "只有资料明确支持时才保留具体事实及 @决策:、@行动:、@开放问题: 标签；"
        "不得编造事实、标签、结论、行动或状态。"
        "不要输出多个候选项、解释、检查过程、前言或其他附加说明。",
        context,
        payload,
        config,
    )


async def project_progress(context, payload, config):
    return await _draft("整理为项目进展摘要，包含进展、风险、下一步。", context, payload, config)


async def user_work_brief_stream(
    context: dict[str, Any], _payload: dict[str, Any], config: dict[str, Any]
) -> AsyncIterator[str]:
    request_payload = {
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
                    "根据项目概览与当前关注事项，生成当前用户的跨项目工作简报。"
                    "突出优先级、风险、临近事项和下一步；不要把它写成某一个项目的进展更新，"
                    "不要编造事实。\n\n"
                    f"资料：{context}"
                ),
            },
        ],
        "temperature": 0.2,
        "stream": True,
    }
    async with httpx.AsyncClient(timeout=float(config["timeout_seconds"])) as client:
        async with client.stream(
            "POST",
            _endpoint(config["base_url"]),
            headers={"Authorization": f"Bearer {config['api_key']}"},
            json=request_payload,
        ) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if not line.startswith("data:"):
                    continue
                payload = line.removeprefix("data:").strip()
                if payload == "[DONE]":
                    break
                event = json.loads(payload)
                text = event.get("choices", [{}])[0].get("delta", {}).get("content")
                if isinstance(text, str) and text:
                    yield text


async def stream_only_action(_context, _payload, _config):
    raise RuntimeError("this action is available only through the stream endpoint")


async def action_suggestions(context, payload, config):
    return await _draft(
        "根据当前讨论，生成一项可直接填写到“行动内容”中的行动项内容。"
        "只输出可编辑的 Markdown 文本；不要列出检查流程、会议状态或多个候选项。"
        "资料中的 agenda_outcome_tags、议题备注、时长和成果均来自服务器；只作建议，不直接写入。",
        context,
        payload,
        config,
    )


async def decision_suggestions(context, payload, config):
    return await _draft(
        "根据当前讨论，生成一项可直接填写到“决策内容”中的决策内容。"
        "只输出可编辑的 Markdown 文本；不要添加标题、实施计划或多个候选项。"
        "资料中的 agenda_outcome_tags、议题备注、时长和成果均来自服务器；只作建议，不直接写入。",
        context,
        payload,
        config,
    )


async def open_question_suggestions(context, payload, config):
    return await _draft(
        "根据当前讨论，生成一项可直接填写到“开放问题内容”中的问题内容。"
        "只输出可编辑的 Markdown 文本；不要假设问题已经解决。"
        "资料中的 agenda_outcome_tags、议题备注、时长和成果均来自服务器；只作建议，不直接写入。",
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
    stream_input = {"type": "object", "additionalProperties": False}
    registry.register_meeting_action(
        MeetingAction(
            action_id="ai-work-assistant.user_work_brief",
            label="生成工作简报",
            description="基于当前用户全部项目生成只读跨项目工作简报",
            admin_only=False,
            input_schema=stream_input,
            output_schema={"type": "object"},
            handler=stream_only_action,
            stream_handler=user_work_brief_stream,
            target_types=("user",),
        )
    )
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
            action_id="ai-work-assistant.agenda_notes",
            label="AI 整理议题记录",
            description="基于当前议题和会议上下文整理可编辑议题记录",
            admin_only=False,
            input_schema=editor_input,
            output_schema=common_output,
            handler=agenda_notes,
            target_types=("agenda_item",),
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
