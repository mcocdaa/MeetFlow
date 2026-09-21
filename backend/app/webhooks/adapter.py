from __future__ import annotations

import base64
import hashlib
import hmac
import time
from typing import Any, Literal
from urllib.parse import quote_plus

import httpx

from app.errors import AppError

WebhookType = Literal["feishu", "dingtalk", "generic"]


def format_feishu_card(
    meeting_title: str,
    project_name: str,
    completed_at_str: str,
    summary: str,
    decisions: list[str],
    actions: list[str],
) -> dict[str, Any]:
    decision_text = "\n".join(f"• {d}" for d in decisions) if decisions else "无"
    action_text = "\n".join(f"• {a}" for a in actions) if actions else "无"

    elements: list[dict[str, Any]] = [
        {
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": f"**所属项目**：{project_name}\n**定稿时间**：{completed_at_str}",
            },
        },
        {"tag": "hr"},
    ]

    if summary.strip():
        elements.extend([
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": f"**📝 会议纪要**：\n{summary.strip()[:1000]}",
                },
            },
            {"tag": "hr"},
        ])

    elements.extend([
        {
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": f"**🎯 决议清单 ({len(decisions)})**：\n{decision_text}",
            },
        },
        {
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": f"**⚡ 待办事项 ({len(actions)})**：\n{action_text}",
            },
        },
    ])

    return {
        "msg_type": "interactive",
        "card": {
            "config": {"wide_screen_mode": True},
            "header": {
                "title": {"tag": "plain_text", "content": f"📋 会议已定稿：{meeting_title}"},
                "template": "blue",
            },
            "elements": elements,
        },
    }


def format_dingtalk_card(
    meeting_title: str,
    project_name: str,
    completed_at_str: str,
    summary: str,
    decisions: list[str],
    actions: list[str],
) -> dict[str, Any]:
    decision_text = "\n".join(f"- {d}" for d in decisions) if decisions else "无"
    action_text = "\n".join(f"- {a}" for a in actions) if actions else "无"

    md_lines = [
        f"### 📋 会议已定稿：{meeting_title}",
        f"- **项目**：{project_name}",
        f"- **定稿时间**：{completed_at_str}",
    ]
    if summary.strip():
        md_lines.extend(["\n#### 📝 会议纪要", summary.strip()[:1000]])
    md_lines.extend([
        f"\n#### 🎯 决议清单 ({len(decisions)})",
        decision_text,
        f"\n#### ⚡ 待办事项 ({len(actions)})",
        action_text,
    ])

    return {
        "msgtype": "markdown",
        "markdown": {
            "title": f"📋 会议已定稿：{meeting_title}",
            "text": "\n\n".join(md_lines),
        },
    }


def format_generic_card(
    meeting_title: str,
    project_name: str,
    completed_at_str: str,
    summary: str,
    decisions: list[str],
    actions: list[str],
) -> dict[str, Any]:
    return {
        "event": "meeting.finalized",
        "title": meeting_title,
        "project": project_name,
        "completed_at": completed_at_str,
        "summary": summary,
        "decisions": decisions,
        "actions": actions,
    }


async def dispatch_webhook(
    webhook_url: str,
    webhook_type: WebhookType,
    payload: dict[str, Any],
    secret: str | None = None,
) -> dict[str, Any]:
    url = webhook_url
    headers = {"Content-Type": "application/json"}
    body = payload

    if webhook_type == "dingtalk" and secret:
        timestamp = str(round(time.time() * 1000))
        secret_enc = secret.encode("utf-8")
        string_to_sign = f"{timestamp}\n{secret}".encode("utf-8")
        hmac_code = hmac.new(secret_enc, string_to_sign, digestmod=hashlib.sha256).digest()
        sign = quote_plus(base64.b64encode(hmac_code).decode("utf-8"))
        url = f"{webhook_url}&timestamp={timestamp}&sign={sign}" if "?" in webhook_url else f"{webhook_url}?timestamp={timestamp}&sign={sign}"

    elif webhook_type == "feishu" and secret:
        timestamp = str(int(time.time()))
        string_to_sign = f"{timestamp}\n{secret}".encode("utf-8")
        hmac_code = hmac.new(string_to_sign, b"", digestmod=hashlib.sha256).digest()
        sign = base64.b64encode(hmac_code).decode("utf-8")
        body["timestamp"] = timestamp
        body["sign"] = sign

    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            response = await client.post(url, json=body, headers=headers)
            if response.status_code >= 400:
                raise AppError(
                    502,
                    "webhook_dispatch_failed",
                    f"Webhook返回错误状态码: {response.status_code}",
                )
            try:
                return response.json()
            except Exception:
                return {"status": "ok", "http_status": response.status_code}
        except httpx.HTTPError as exc:
            raise AppError(502, "webhook_dispatch_failed", f"Webhook发送失败: {str(exc)}")
