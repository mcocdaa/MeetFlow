"""OpenAI-compatible draft generation for MeetFlow.

This plugin deliberately has no MeetFlow write access.  Each result is a draft
that a user must review and apply through the core application's normal APIs.
"""

from typing import Any

import httpx

from app.plugins.contracts import MeetingAction
from app.meetings.models import Meeting
from app.meetings.schemas import MeetingEdit
from app.meetings.service import MeetingService
from app.outcomes.schemas import ActionWrite
from app.outcomes.service import OutcomeService
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
    draft = await _draft("建议可执行的行动项，使用清晰的 Markdown 列表。", context, payload, config)
    candidates = []
    for line in draft["markdown"].splitlines():
        text = line.strip().lstrip("-*").strip()
        if text and not text.startswith("#"):
            candidates.append({"content": text[:1000]})
    return {**draft, "candidates": candidates}


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


def apply_action_suggestions(job, payload, actor, session):
    stored = (job.result_json or {}).get("candidates")
    if not isinstance(stored, list):
        raise ValueError("job has no action candidates")
    candidates = payload.get("candidates")
    if not isinstance(candidates, list):
        selected_indexes = payload.get("selected_indexes", [])
        if not isinstance(selected_indexes, list):
            selected_indexes = []
        candidates = [
            {"index": index, **stored[index]}
            for index in selected_indexes
            if isinstance(index, int)
            and 0 <= index < len(stored)
            and isinstance(stored[index], dict)
        ]
    selected = {
        candidate.get("index"): candidate
        for candidate in candidates
        if isinstance(candidate, dict) and isinstance(candidate.get("index"), int)
    }
    if not selected or any(
        index < 0 or index >= len(stored) for index in selected
    ):
        raise ValueError("invalid action candidate selection")
    if any(
        not isinstance(candidate.get("content"), str)
        or not candidate["content"].strip()
        for candidate in selected.values()
    ):
        raise ValueError("invalid action candidate")
    meeting = session.get(Meeting, job.target_id)
    if meeting is None or job.target_type != "meeting":
        raise ValueError("meeting target is missing")
    for candidate in selected.values():
        OutcomeService(session).create_action(
            meeting.project_id,
            ActionWrite(
                project_id=meeting.project_id,
                meeting_id=meeting.id,
                content=candidate["content"],
                owner_user_id=candidate.get("owner_user_id"),
                due_date=candidate.get("due_date"),
                priority=candidate.get("priority", "normal"),
            ),
            actor,
        )
    return {"created_count": len(selected)}


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
            label="建议行动项",
            description="基于会议资料生成待确认行动项建议",
            admin_only=False,
            input_schema=editor_input,
            output_schema={
                "type": "object",
                "required": ["markdown", "model", "candidates"],
            },
            handler=action_suggestions,
            apply_handler=apply_action_suggestions,
            target_types=("meeting",),
        )
    )
