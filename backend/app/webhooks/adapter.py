from __future__ import annotations

import base64
import hashlib
import hmac
import ipaddress
import os
import socket
import time
from typing import Any, Literal
from urllib.parse import quote_plus, urlsplit, urlunsplit

import httpx

from app.errors import AppError

WebhookType = Literal["feishu", "dingtalk", "generic"]

_BLOCKED_NETWORKS = (
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
)


def _is_blocked_ip(ip_obj: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    if isinstance(ip_obj, ipaddress.IPv6Address) and ip_obj.ipv4_mapped is not None:
        ip_obj = ip_obj.ipv4_mapped
    return (
        any(ip_obj in net for net in _BLOCKED_NETWORKS)
        or ip_obj.is_loopback
        or ip_obj.is_private
        or ip_obj.is_link_local
        or ip_obj.is_unspecified
        or ip_obj.is_multicast
    )


def validate_webhook_url(webhook_url: str, *, allow_private: bool = False) -> None:
    raw = (webhook_url or "").strip()
    parsed = urlsplit(raw)
    scheme = parsed.scheme.lower()
    hostname = (parsed.hostname or "").strip().lower()
    if scheme not in ("http", "https") or not hostname:
        raise AppError(
            422,
            "invalid_webhook_url",
            "Webhook 地址必须使用 http:// 或 https:// 协议",
        )

    if allow_private or os.getenv("MEETFLOW_WEBHOOK_ALLOW_PRIVATE") == "1":
        return

    if hostname in {"localhost", "localhost.localdomain"} or hostname.endswith(
        (".local", ".internal")
    ):
        raise AppError(
            422,
            "invalid_webhook_url",
            "禁止将 Webhook 发送至本地或内网地址",
        )

    try:
        literal_ip = ipaddress.ip_address(hostname)
    except ValueError:
        literal_ip = None

    if literal_ip is not None:
        if _is_blocked_ip(literal_ip):
            raise AppError(
                422,
                "invalid_webhook_url",
                "禁止将 Webhook 发送至本地或内网地址",
            )
        return

    port = parsed.port or (443 if scheme == "https" else 80)
    try:
        addr_infos = socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
    except socket.gaierror:
        return

    for info in addr_infos:
        raw_ip = str(info[4][0]).split("%", 1)[0]
        try:
            resolved_ip = ipaddress.ip_address(raw_ip)
        except ValueError:
            continue
        if _is_blocked_ip(resolved_ip):
            raise AppError(
                422,
                "invalid_webhook_url",
                "禁止将 Webhook 发送至本地或内网地址",
            )


def redact_webhook_url(webhook_url: str) -> str:
    parsed = urlsplit((webhook_url or "").strip())
    if not parsed.scheme or not parsed.netloc:
        return "***"
    path_parts = [part for part in parsed.path.split("/") if part]
    if len(path_parts) > 1:
        redacted_path = "/" + "/".join([*path_parts[:-1], "***"])
    elif path_parts:
        redacted_path = "/***"
    else:
        redacted_path = ""
    redacted_query = "***" if parsed.query else ""
    return urlunsplit((parsed.scheme, parsed.netloc, redacted_path, redacted_query, ""))


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
    *,
    allow_private: bool = False,
) -> dict[str, Any]:
    validate_webhook_url(webhook_url, allow_private=allow_private)
    url = webhook_url.strip()
    headers = {"Content-Type": "application/json"}
    body = dict(payload)

    if webhook_type == "dingtalk" and secret:
        timestamp = str(round(time.time() * 1000))
        secret_enc = secret.encode("utf-8")
        string_to_sign = f"{timestamp}\n{secret}".encode("utf-8")
        hmac_code = hmac.new(secret_enc, string_to_sign, digestmod=hashlib.sha256).digest()
        sign = quote_plus(base64.b64encode(hmac_code).decode("utf-8"))
        url = f"{url}&timestamp={timestamp}&sign={sign}" if "?" in url else f"{url}?timestamp={timestamp}&sign={sign}"

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
