#!/usr/bin/env python3
"""MeetFlow API 冒烟：每个功能一个真实例子。

会写入真实数据，请只对一次性/测试实例运行。用法：

    .venv/bin/python scripts/smoke_api.py --base-url http://127.0.0.1:8000 \
        --admin-password "$ADMIN_PASSWORD"

参数也可用环境变量提供：MEETFLOW_BASE_URL、MEETFLOW_ADMIN_USERNAME、
MEETFLOW_ADMIN_PASSWORD、MEETFLOW_MEMBER_PASSWORD。
"""
from __future__ import annotations

import argparse
import os
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone

import httpx

BASE = os.environ.get("MEETFLOW_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
ADMIN_USER = os.environ.get("MEETFLOW_ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.environ.get(
    "MEETFLOW_ADMIN_PASSWORD", "development-admin-password"
)
MEMBER_PASSWORD = os.environ.get("MEETFLOW_MEMBER_PASSWORD", "smoke-member-password")

NOW = datetime.now(timezone.utc)
STATE: dict = {}
RESULTS: list[tuple[str, str, str]] = []


def iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def client() -> httpx.Client:
    return httpx.Client(base_url=BASE, timeout=30)


def req(c, method, path, *, expect=200, code=None, **kw):
    response = c.request(method, path, **kw)
    if response.status_code != expect:
        raise AssertionError(
            f"{method} {path} -> {response.status_code}, expected {expect}: "
            f"{response.text[:400]}"
        )
    if code is not None:
        actual = (response.json().get("error") or {}).get("code")
        if actual != code:
            raise AssertionError(
                f"{method} {path} code={actual!r}, expected {code!r}: "
                f"{response.text[:300]}"
            )
    return response


def check(condition, message):
    if not condition:
        raise AssertionError(message)


def meeting_version(mid: str) -> int:
    return req(STATE["admin"], "GET", f"/api/meetings/{mid}").json()["version"]


def agenda_in(mid: str, aid: str) -> dict:
    data = req(STATE["admin"], "GET", f"/api/meetings/{mid}").json()
    for item in data["agenda_items"]:
        if item["id"] == aid:
            return item
    raise AssertionError(f"agenda {aid} not found in meeting {mid}")


# ---------------------------------------------------------------------------
# 每个功能一个例子
# ---------------------------------------------------------------------------


def s_infra() -> str:
    c = client()
    check(req(c, "GET", "/api/health").json()["status"] == "ok", "health")
    ready = req(c, "GET", "/api/health/ready").json()
    check(
        ready["database"] == "ok" and ready["plugins"] == "ok",
        str(ready),
    )
    version = req(c, "GET", "/api/meta").json()["version"]
    return f"database/plugins/worker 就绪，version={version}"


def s_auth() -> str:
    admin = client()
    STATE["admin"] = admin
    req(
        client(),
        "POST",
        "/api/auth/login",
        json={"username": ADMIN_USER, "password": "wrong"},
        expect=401,
        code="invalid_credentials",
    )
    req(
        admin,
        "POST",
        "/api/auth/login",
        json={"username": ADMIN_USER, "password": ADMIN_PASSWORD},
    )
    me = req(admin, "GET", "/api/auth/me").json()
    STATE["admin_id"] = me["id"]
    check(me["role"] == "admin", str(me))
    session = req(admin, "GET", "/api/auth/session").json()
    check(session["user"]["username"] == ADMIN_USER, str(session))
    check(
        req(client(), "GET", "/api/auth/config").json()["allow_registration"]
        is True,
        "registration config",
    )

    suffix = uuid.uuid4().hex[:6]
    names = {key: f"smoke-{key}-{suffix}" for key in ("anna", "ben", "cara", "reject")}
    for key in ("anna", "ben", "reject"):
        req(
            client(),
            "POST",
            "/api/auth/register",
            json={
                "username": names[key],
                "display_name": key.title(),
                "password": MEMBER_PASSWORD,
            },
            expect=201,
        )
    pending = req(admin, "GET", "/api/admin/users", params={"status": "pending"}).json()
    ids = {row["username"]: row["id"] for row in pending}
    STATE["anna_id"] = ids[names["anna"]]
    STATE["ben_id"] = ids[names["ben"]]
    req(admin, "POST", f"/api/admin/users/{STATE['anna_id']}/approve")
    req(admin, "POST", f"/api/admin/users/{STATE['ben_id']}/approve")

    cara = req(
        admin,
        "POST",
        "/api/admin/users",
        json={
            "username": names["cara"],
            "display_name": "Cara",
            "password": MEMBER_PASSWORD,
        },
        expect=201,
    ).json()
    STATE["cara_id"] = cara["id"]

    new_password = "smoke-ben-new-password"
    req(
        admin,
        "POST",
        f"/api/admin/users/{STATE['ben_id']}/reset-password",
        json={"password": new_password},
        expect=204,
    )
    ben = client()
    req(
        ben,
        "POST",
        "/api/auth/login",
        json={"username": names["ben"], "password": new_password},
    )
    req(
        admin,
        "POST",
        f"/api/admin/users/{STATE['ben_id']}/reset-password",
        json={"password": MEMBER_PASSWORD},
        expect=204,
    )

    req(admin, "POST", f"/api/admin/users/{ids[names['reject']]}/reject")
    req(
        client(),
        "POST",
        "/api/auth/login",
        json={"username": names["reject"], "password": MEMBER_PASSWORD},
        expect=403,
        code="account_rejected",
    )
    req(admin, "POST", f"/api/admin/users/{STATE['cara_id']}/disable")
    req(
        client(),
        "POST",
        "/api/auth/login",
        json={"username": names["cara"], "password": MEMBER_PASSWORD},
        expect=403,
        code="account_disabled",
    )
    req(admin, "POST", f"/api/admin/users/{STATE['cara_id']}/restore")

    anna = client()
    req(
        anna,
        "POST",
        "/api/auth/login",
        json={"username": names["anna"], "password": MEMBER_PASSWORD},
    )
    ben = client()
    req(
        ben,
        "POST",
        "/api/auth/login",
        json={"username": names["ben"], "password": MEMBER_PASSWORD},
    )
    STATE["anna"] = anna
    STATE["ben"] = ben
    return "登录/注册/审批/拒绝/禁用/恢复/重置密码 全部通过"


def s_projects() -> str:
    admin = STATE["admin"]
    slug = f"smoke-project-{uuid.uuid4().hex[:8]}"
    project = req(
        admin,
        "POST",
        "/api/projects",
        json={
            "name": "烟雾测试项目",
            "slug": slug,
            "summary": "验证重构后的本地部署",
            "description_markdown": "# 目标\n端到端检查",
            "status": "active",
            "health": "on_track",
            "lead_user_id": STATE["admin_id"],
            "target_date": "2026-12-31",
            "member_ids": [STATE["anna_id"]],
        },
        expect=201,
    ).json()
    STATE["project_id"] = project["id"]

    listed = req(admin, "GET", "/api/projects").json()
    check(any(row["slug"] == slug for row in listed), "project not in list")

    detail = req(admin, "GET", f"/api/projects/{project['id']}").json()
    check(detail["capabilities"]["can_manage"] is True, str(detail.get("capabilities")))
    member_ids = {row["user"]["id"] for row in detail["memberships"]}
    check({STATE["admin_id"], STATE["anna_id"]} <= member_ids, "memberships")

    updated = req(
        admin,
        "PUT",
        f"/api/projects/{project['id']}",
        json={"expected_version": detail["version"], "summary": "更新后的摘要"},
    ).json()
    check(updated["version"] == detail["version"] + 1, "version bump")
    stale = req(
        admin,
        "PUT",
        f"/api/projects/{project['id']}",
        json={"expected_version": detail["version"], "summary": "过期写入"},
        expect=409,
        code="version_conflict",
    )
    stale_details = stale.json()["error"].get("details") or {}
    check(
        "expected_version" in stale_details and "actual_version" in stale_details,
        f"conflict details: {stale.text[:200]}",
    )

    progress = req(
        admin,
        "POST",
        f"/api/projects/{project['id']}/updates",
        json={"health": "on_track", "content_markdown": "完成本地部署检查"},
        expect=201,
    ).json()
    edited = req(
        admin,
        "PUT",
        f"/api/project-updates/{progress['id']}",
        json={
            "health": "at_risk",
            "content_markdown": "发现一个风险点",
            "expected_version": progress["version"],
        },
    ).json()
    check(
        edited["health"] == "at_risk" and edited["version"] == progress["version"] + 1,
        "progress edit",
    )
    updates = req(admin, "GET", f"/api/projects/{project['id']}/updates").json()
    check(
        len(updates) == 1 and updates[0]["content_markdown"] == "发现一个风险点",
        f"updates={updates}",
    )
    activity = req(admin, "GET", f"/api/projects/{project['id']}/activity").json()
    check(
        any(row["event_type"] == "project.created" for row in activity["items"]),
        "activity missing",
    )
    return f"创建/列表/详情/更新/409(带版本详情)/进展编辑/活动 OK（slug={slug}）"


def s_series() -> str:
    admin = STATE["admin"]
    pid = STATE["project_id"]
    anchor = datetime.now(timezone.utc).date() - timedelta(days=3)
    series = req(
        admin,
        "POST",
        f"/api/projects/{pid}/meeting-series",
        json={
            "title": "每日站会",
            "purpose_markdown": "同步进度",
            "recurrence_description": "每天 09:00",
            "recurrence_frequency": "daily",
            "recurrence_interval": 1,
            "recurrence_local_time": "09:00:00",
            "recurrence_timezone": "Asia/Shanghai",
            "recurrence_anchor_date": anchor.isoformat(),
            "default_duration_minutes": 30,
            "default_host_user_id": STATE["admin_id"],
            "default_recorder_user_id": STATE["anna_id"],
            "status": "active",
            "participants": [
                {"user_id": STATE["anna_id"], "participation_role": "attendee"}
            ],
            "standing_items": [
                {
                    "title": "进度同步",
                    "agenda_type": "discussion",
                    "default_owner_user_id": STATE["anna_id"],
                    "default_duration_minutes": 10,
                }
            ],
        },
        expect=201,
    ).json()
    STATE["series_id"] = series["id"]
    listed = req(admin, "GET", f"/api/projects/{pid}/meeting-series").json()
    check(any(row["id"] == series["id"] for row in listed), "series list")
    detail = req(admin, "GET", f"/api/meeting-series/{series['id']}").json()
    check(detail["recurrence"]["frequency"] == "daily", "recurrence")
    req(
        admin,
        "PUT",
        f"/api/meeting-series/{series['id']}",
        json={"expected_version": detail["version"], "title": "每日站会（更新）"},
    )

    meetings = req(admin, "GET", f"/api/projects/{pid}/meetings").json()
    occurrences = [
        row
        for row in meetings
        if row["series"] and row["series"]["id"] == series["id"]
    ]
    check(len(occurrences) >= 3, f"materialized={len(occurrences)}")
    check(
        all(row["occurrence_kind"] == "scheduled" for row in occurrences),
        "occurrence kind",
    )

    start = NOW + timedelta(days=2)
    manual = req(
        admin,
        "POST",
        f"/api/meeting-series/{series['id']}/occurrences",
        json={
            "title": "临时对齐会",
            "scheduled_start": iso(start),
            "scheduled_end": iso(start + timedelta(hours=1)),
        },
        expect=201,
    ).json()
    check(manual["occurrence_kind"] == "manual", "manual occurrence")
    STATE["manual_meeting_id"] = manual["id"]
    return f"系列增改查 + {len(occurrences)} 个周期实例自动补齐 + 临时实例 OK"


def s_meeting_agenda() -> str:
    admin = STATE["admin"]
    pid = STATE["project_id"]
    start = NOW + timedelta(days=1)
    meeting = req(
        admin,
        "POST",
        f"/api/projects/{pid}/meetings",
        json={
            "title": "重构验收会",
            "purpose_markdown": "检查后端重构",
            "scheduled_start": iso(start),
            "scheduled_end": iso(start + timedelta(hours=1)),
            "host_user_id": STATE["admin_id"],
            "recorder_user_id": STATE["anna_id"],
            "participants": [
                {"user_id": STATE["anna_id"], "participation_role": "attendee"},
                {"user_id": STATE["ben_id"], "participation_role": "attendee"},
            ],
        },
        expect=201,
    ).json()
    mid = STATE["meeting_id"] = meeting["id"]

    detail = req(admin, "GET", f"/api/meetings/{mid}").json()
    check(detail["capabilities"]["can_manage"] is True, "capabilities")
    stale = detail["version"]
    req(
        admin,
        "PUT",
        f"/api/meetings/{mid}",
        json={"expected_version": stale, "title": "重构验收会（正式）"},
    )
    req(
        admin,
        "PUT",
        f"/api/meetings/{mid}",
        json={"expected_version": stale, "title": "过期标题"},
        expect=409,
        code="version_conflict",
    )

    def add_item(**payload) -> dict:
        version = meeting_version(mid)
        return req(
            admin,
            "POST",
            f"/api/meetings/{mid}/agenda-items",
            params={"expected_meeting_version": version},
            json=payload,
            expect=201,
        ).json()

    item1 = add_item(
        title="后端结构回顾",
        agenda_type="discussion",
        presenter_user_id=STATE["anna_id"],
        estimated_minutes=15,
        notes_markdown="回顾双路径改造",
    )
    item2 = add_item(
        title="成果演示",
        agenda_type="information",
        notes_markdown=(
            "@决策: 采用共享 resolve_stale\n"
            "@行动: 更新开发文档\n"
            "@开放问题: 是否需要更多回归测试"
        ),
    )
    item3 = add_item(title="遗留问题讨论", agenda_type="discussion")
    check(
        all(item["position"] == index for index, item in enumerate((item1, item2, item3))),
        "initial positions",
    )

    reordered = req(
        admin,
        "POST",
        f"/api/meetings/{mid}/agenda-items/reorder",
        json={
            "ids": [item3["id"], item1["id"], item2["id"]],
            "expected_meeting_version": meeting_version(mid),
        },
    ).json()
    check([row["id"] for row in reordered] == [item3["id"], item1["id"], item2["id"]], "reorder")

    current_item1 = agenda_in(mid, item1["id"])
    updated = req(
        admin,
        "PUT",
        f"/api/agenda-items/{item1['id']}",
        json={
            "expected_version": current_item1["version"],
            "title": "后端结构回顾（更新）",
        },
    ).json()
    check(updated["title"].endswith("（更新）"), "agenda update")

    removable = add_item(title="待删除议题", agenda_type="discussion")
    req(
        admin,
        "DELETE",
        f"/api/agenda-items/{removable['id']}",
        params={"expected_meeting_version": meeting_version(mid)},
        json={"expected_version": removable["version"]},
        expect=204,
    )
    after_delete = req(admin, "GET", f"/api/meetings/{mid}").json()
    check(
        all(row["id"] != removable["id"] for row in after_delete["agenda_items"]),
        "agenda delete",
    )

    movable = add_item(title="迁移到临时会", agenda_type="information")
    moved = req(
        admin,
        "POST",
        f"/api/agenda-items/{movable['id']}/move",
        json={
            "target_meeting_id": STATE["manual_meeting_id"],
            "expected_version": movable["version"],
            "expected_source_meeting_version": meeting_version(mid),
            "expected_target_meeting_version": meeting_version(
                STATE["manual_meeting_id"]
            ),
        },
    ).json()
    check(moved["meeting_id"] == STATE["manual_meeting_id"], "agenda move")

    started = req(
        admin,
        "POST",
        f"/api/meetings/{mid}/start",
        json={"expected_version": meeting_version(mid)},
    ).json()
    check(started["status"] == "in_progress", "meeting start")
    started_agenda = next(
        row for row in started["agenda_items"] if row["status"] == "in_progress"
    )
    check(started_agenda["id"] == item3["id"], "first planned auto-start")

    advanced = req(
        admin,
        "POST",
        f"/api/agenda-items/{item3['id']}/complete-and-advance",
        json={"expected_version": agenda_in(mid, item3["id"])["version"]},
    ).json()
    check(
        advanced["agenda_item"]["status"] == "completed"
        and advanced["next_agenda_item_id"] == item1["id"],
        "complete and advance",
    )
    skipped = req(
        admin,
        "POST",
        f"/api/agenda-items/{item2['id']}/skip",
        json={"expected_version": agenda_in(mid, item2["id"])["version"]},
    ).json()
    check(skipped["status"] == "skipped", "agenda skip")

    STATE["item1_id"] = item1["id"]
    STATE["item2_id"] = item2["id"]
    STATE["item3_id"] = item3["id"]
    return "建会议/更新/409/增删改序/移动/开始自动起议题/完成推进/跳过 OK"


def s_outcomes() -> str:
    admin = STATE["admin"]
    anna = STATE["anna"]
    pid = STATE["project_id"]
    mid = STATE["meeting_id"]

    detail = req(admin, "GET", f"/api/meetings/{mid}").json()
    derived = next(row for row in detail["agenda_items"] if row["id"] == STATE["item2_id"])
    check(
        len(derived["decisions"]) == 1
        and len(derived["actions"]) == 1
        and len(derived["open_questions"]) == 1,
        "derived outcomes from @ tags",
    )

    d1 = req(
        admin,
        "POST",
        f"/api/projects/{pid}/decisions",
        json={
            "meeting_id": mid,
            "title": "采用统一乐观锁工具",
            "decision_markdown": "所有 service 使用 resolve_stale",
            "rationale_markdown": "减少重复",
            "reviewer_ids": [STATE["anna_id"]],
        },
        expect=201,
    ).json()
    reviewed = req(
        anna,
        "POST",
        f"/api/decisions/{d1['id']}/review",
        json={"status": "approved", "comment": "同意", "expected_version": d1["version"]},
    ).json()
    check(reviewed["reviewers"][0]["status"] == "approved", "decision review")
    finalized = req(
        admin,
        "POST",
        f"/api/decisions/{d1['id']}/finalize",
        json={"expected_version": reviewed["version"]},
    ).json()
    check(finalized["status"] == "final", "decision finalize")

    d2 = req(
        admin,
        "POST",
        f"/api/projects/{pid}/decisions",
        json={"meeting_id": mid, "title": "替代决策", "decision_markdown": "v2"},
        expect=201,
    ).json()
    d2_final = req(
        admin,
        "POST",
        f"/api/decisions/{d2['id']}/finalize",
        json={"expected_version": d2["version"]},
    ).json()
    superseded = req(
        admin,
        "POST",
        f"/api/decisions/{d1['id']}/supersede",
        json={
            "new_decision_id": d2["id"],
            "expected_version": finalized["version"],
            "expected_new_version": d2_final["version"],
        },
    ).json()
    check(
        superseded["status"] == "final"
        and superseded["supersedes_decision_id"] == d1["id"],
        "decision supersede",
    )

    d3 = req(
        admin,
        "POST",
        f"/api/projects/{pid}/decisions",
        json={"meeting_id": mid, "title": "待撤回决策", "decision_markdown": "x"},
        expect=201,
    ).json()
    d3_edited = req(
        admin,
        "PUT",
        f"/api/decisions/{d3['id']}",
        json={"expected_version": d3["version"], "title": "待撤回决策（改名）"},
    ).json()
    withdrawn = req(
        admin,
        "POST",
        f"/api/decisions/{d3['id']}/withdraw",
        json={"expected_version": d3_edited["version"]},
    ).json()
    check(withdrawn["status"] == "withdrawn", "decision withdraw")

    pending_review = req(
        admin,
        "POST",
        f"/api/projects/{pid}/decisions",
        json={
            "meeting_id": mid,
            "title": "等待评审的决策",
            "decision_markdown": "留给 attention 检查",
            "reviewer_ids": [STATE["anna_id"]],
        },
        expect=201,
    ).json()
    STATE["pending_decision_id"] = pending_review["id"]

    req(
        admin,
        "POST",
        f"/api/projects/{pid}/decisions",
        json={
            "meeting_id": mid,
            "agenda_item_id": STATE["item3_id"],
            "title": "绑定议题的决策",
            "decision_markdown": "用于迁移示例",
        },
        expect=201,
    )

    action = req(
        admin,
        "POST",
        f"/api/projects/{pid}/actions",
        json={
            "project_id": pid,
            "meeting_id": mid,
            "content": "修正文档链接",
            "owner_user_id": STATE["anna_id"],
            "due_date": (NOW + timedelta(days=2)).date().isoformat(),
            "priority": "high",
        },
        expect=201,
    ).json()
    done = req(
        admin,
        "PUT",
        f"/api/actions/{action['id']}",
        json={"expected_version": action["version"], "status": "done"},
    ).json()
    check(done["status"] == "done" and done["completed_at"], "action done")
    reopened = req(
        admin,
        "PUT",
        f"/api/actions/{action['id']}",
        json={"expected_version": done["version"], "status": "open"},
    ).json()
    check(
        reopened["status"] == "open" and reopened["completed_at"] is None,
        "action reopen",
    )

    q1 = req(
        admin,
        "POST",
        f"/api/projects/{pid}/open-questions",
        json={
            "meeting_id": mid,
            "question_markdown": "是否需要更多回归测试？",
            "owner_user_id": STATE["ben_id"],
        },
        expect=201,
    ).json()
    q1_edited = req(
        admin,
        "PUT",
        f"/api/open-questions/{q1['id']}",
        json={
            "expected_version": q1["version"],
            "question_markdown": "是否需要更多回归测试（更新）？",
        },
    ).json()
    scheduled = req(
        admin,
        "POST",
        f"/api/open-questions/{q1['id']}/schedule",
        json={
            "meeting_id": STATE["manual_meeting_id"],
            "expected_version": q1_edited["version"],
            "expected_meeting_version": meeting_version(STATE["manual_meeting_id"]),
        },
        expect=201,
    ).json()
    check(scheduled["carry_from_open_question_id"] == q1["id"], "question schedule")

    q2 = req(
        admin,
        "POST",
        f"/api/projects/{pid}/open-questions",
        json={"meeting_id": mid, "question_markdown": "如何验证？"},
        expect=201,
    ).json()
    resolved = req(
        admin,
        "POST",
        f"/api/open-questions/{q2['id']}/resolve",
        json={"decision_id": d2["id"], "expected_version": q2["version"]},
    ).json()
    check(
        resolved["status"] == "resolved"
        and resolved["resolved_by_decision_id"] == d2["id"],
        "question resolve",
    )
    return "标签派生成果 + 决策评审/定稿/撤回/替代 + 行动完成/重开 + 问题排期/解决 OK"


def s_comments() -> str:
    admin = STATE["admin"]
    anna = STATE["anna"]
    mid = STATE["meeting_id"]

    root = req(
        admin,
        "POST",
        "/api/comments",
        json={
            "target_type": "meeting",
            "target_id": mid,
            "body_markdown": "请 @anna 确认验收清单",
            "mention_user_ids": [STATE["anna_id"]],
        },
        expect=201,
    ).json()
    check(root["can_edit"] and root["can_delete"], "admin comment permissions")
    reply = req(
        anna,
        "POST",
        "/api/comments",
        json={
            "target_type": "meeting",
            "target_id": mid,
            "parent_id": root["id"],
            "body_markdown": "收到，另请 @ben 关注",
            "mention_user_ids": [STATE["ben_id"]],
        },
        expect=201,
    ).json()
    check(reply["parent_id"] == root["id"], "reply parent")

    page = req(
        admin,
        "GET",
        "/api/comments",
        params={"target_type": "meeting", "target_id": mid},
    ).json()
    listed_root = next(row for row in page["items"] if row["id"] == root["id"])
    check([row["id"] for row in listed_root["replies"]] == [reply["id"]], "thread")

    edited = req(
        admin,
        "PUT",
        f"/api/comments/{root['id']}",
        json={
            "expected_version": root["version"],
            "body_markdown": "请 @anna 复核验收清单（已更新）",
            "mention_user_ids": [STATE["anna_id"]],
        },
    ).json()
    resolved = req(
        admin,
        "POST",
        f"/api/comments/{root['id']}/resolve",
        json={"expected_version": edited["version"]},
    ).json()
    check(resolved["resolved_at"], "comment resolve")
    reopened = req(
        admin,
        "POST",
        f"/api/comments/{root['id']}/reopen",
        json={"expected_version": resolved["version"]},
    ).json()
    check(reopened["resolved_at"] is None, "comment reopen")

    replies = req(admin, "GET", f"/api/comments/{root['id']}/replies").json()
    check(len(replies["items"]) == 1, "reply pagination")
    req(
        anna,
        "DELETE",
        f"/api/comments/{reply['id']}",
        json={"expected_version": reply["version"]},
        expect=204,
    )
    return "创建/回复/提及/线程列表/编辑/解决/重开/删除 OK"


def s_attachments() -> str:
    admin = STATE["admin"]
    pid = STATE["project_id"]
    mid = STATE["meeting_id"]
    content = f"# smoke attachment\n{uuid.uuid4().hex}\n".encode()
    uploaded = req(
        admin,
        "POST",
        f"/api/attachments/project/{pid}",
        files={"file": ("smoke-note.md", content, "text/markdown")},
        expect=201,
    ).json()
    check(
        uploaded["original_name"] == "smoke-note.md" and uploaded["can_delete"] is True,
        str(uploaded),
    )
    listed = req(admin, "GET", f"/api/attachments/project/{pid}").json()
    check(any(row["id"] == uploaded["id"] for row in listed), "attachment list")
    download = req(admin, "GET", f"/api/attachments/project/{pid}/{uploaded['id']}")
    check(download.content == content, "download content")
    preview = req(
        admin, "GET", f"/api/attachments/project/{pid}/{uploaded['id']}/preview"
    )
    check("smoke attachment" in preview.text, "preview content")

    req(
        admin,
        "POST",
        f"/api/attachments/meeting/{mid}",
        files={"file": ("meeting-note.txt", b"meeting attachment", "text/plain")},
        expect=201,
    )
    req(
        admin,
        "POST",
        f"/api/attachments/agenda_item/{STATE['item1_id']}",
        files={"file": ("agenda-note.md", b"agenda attachment", "text/markdown")},
        expect=201,
    )
    req(
        admin,
        "DELETE",
        f"/api/attachments/project/{pid}/{uploaded['id']}",
        expect=204,
    )
    listed = req(admin, "GET", f"/api/attachments/project/{pid}").json()
    check(not any(row["id"] == uploaded["id"] for row in listed), "attachment delete")
    return "项目/会议/议题附件：上传/列表/下载/预览/删除 OK"


def s_meeting_detail_shape() -> str:
    admin = STATE["admin"]
    detail = req(admin, "GET", f"/api/meetings/{STATE['meeting_id']}").json()
    check("attachments" in detail and "agenda_items" in detail, "meeting detail shape")
    return "会议详情包含 attachments/agenda_items 投影 OK"


def s_inbox() -> str:
    anna = STATE["anna"]
    inbox = req(anna, "GET", "/api/inbox").json()
    check(inbox["unread_count"] > 0, f"unread={inbox['unread_count']}")
    kinds = {row["kind"] for row in inbox["items"]}
    check(
        {"action.assigned", "decision.review_requested", "comment.mention"} & kinds,
        str(kinds),
    )
    changes = req(anna, "GET", "/api/inbox/changes", params={"cursor": 0}).json()
    check(changes["notifications"], "changes empty")
    first = changes["notifications"][0]
    req(anna, "POST", f"/api/inbox/{first['id']}/read", expect=204)
    after = req(anna, "GET", "/api/inbox").json()
    check(after["unread_count"] == inbox["unread_count"] - 1, "unread decrement")
    req(anna, "POST", "/api/inbox/read-all", expect=204)
    check(req(anna, "GET", "/api/inbox").json()["unread_count"] == 0, "read all")

    attention = req(anna, "GET", "/api/attention").json()
    check(attention["items"], "attention empty")
    reasons = {reason for item in attention["items"] for reason in item["reasons"]}
    check(
        "decision_review_pending" in reasons or "action_due_soon" in reasons,
        str(reasons),
    )
    return f"未读={inbox['unread_count']}，类型={sorted(kinds)}，读单条/全部/attention OK"


def s_lifecycle() -> str:
    admin = STATE["admin"]
    mid = STATE["meeting_id"]
    finished = req(
        admin,
        "POST",
        f"/api/meetings/{mid}/finish",
        json={"expected_version": meeting_version(mid)},
    ).json()
    check(finished["status"] == "completed" and finished["completed_at"], "finish")

    detail = req(admin, "GET", f"/api/meetings/{mid}").json()
    check(
        detail["current_snapshot"]["completion_number"] == 1,
        "snapshot completion_number",
    )
    check(
        detail["current_snapshot"]["snapshot_json"]["meeting"]["title"]
        == "重构验收会（正式）",
        "snapshot content",
    )
    check(
        all(
            item["status"] in {"completed", "skipped", "canceled"}
            for item in detail["agenda_items"]
        ),
        "agenda finalized on finish",
    )
    snapshots = req(admin, "GET", f"/api/meetings/{mid}/snapshots").json()
    check(len(snapshots) == 1, "snapshots list")

    amendment = req(
        admin,
        "POST",
        f"/api/meetings/{mid}/amendments",
        json={
            "reason": "补充纪要",
            "content_markdown": "会后补充：部署已验证",
            "expected_version": detail["version"],
        },
        expect=201,
    ).json()
    check(amendment["content_markdown"], "amendment")

    reopened = req(
        admin,
        "POST",
        f"/api/meetings/{mid}/reopen",
        json={"expected_version": meeting_version(mid)},
    ).json()
    check(reopened["status"] == "in_progress", "reopen")
    req(
        admin,
        "POST",
        f"/api/meetings/{mid}/finish",
        json={"expected_version": meeting_version(mid)},
    )
    detail2 = req(admin, "GET", f"/api/meetings/{mid}").json()
    check(
        detail2["current_snapshot"]["completion_number"] == 2,
        "second completion snapshot",
    )
    check(len(detail2["amendments"]) == 1, "amendment persisted")

    canceled = req(
        admin,
        "POST",
        f"/api/meetings/{STATE['manual_meeting_id']}/cancel",
        json={"expected_version": meeting_version(STATE["manual_meeting_id"])},
    ).json()
    check(canceled["status"] == "canceled", "cancel")
    return "完成→快照1→更正→重开→再完成→快照2 + 取消 OK"


def s_workspace() -> str:
    admin = STATE["admin"]
    meetings = req(admin, "GET", "/api/meetings", params={"limit": 50}).json()
    check(
        any(row["id"] == STATE["meeting_id"] for row in meetings["items"]),
        "global meetings",
    )
    decisions = req(admin, "GET", "/api/decisions").json()
    check(decisions["items"], "global decisions")
    actions = req(admin, "GET", "/api/actions").json()
    check(actions["items"], "global actions")
    brief = req(admin, "GET", "/api/work-brief").json()
    check("content_markdown" in brief, "work brief shape")
    return "全局会议/决策/行动列表 + 工作简报 OK"


def s_plugins() -> str:
    admin = STATE["admin"]
    plugins = req(admin, "GET", "/api/admin/plugins").json()
    by_id = {row["id"]: row for row in plugins["plugins"]}
    check("ai-work-assistant" in by_id, str(by_id))
    check(by_id["ai-work-assistant"]["loaded"] is True, "ai plugin loaded")
    check(by_id["meeting-export"]["loaded"] is True, "export plugin loaded")

    config = req(
        admin,
        "PUT",
        "/api/admin/plugins/ai-work-assistant/config",
        json={
            "base_url": "http://127.0.0.1:9/v1",
            "model": "smoke-model",
            "timeout_seconds": 5,
            "api_key": "smoke-key",
        },
    ).json()
    check(
        config["base_url"] == "http://127.0.0.1:9/v1"
        and config["api_key"] == {"configured": True},
        str(config),
    )
    req(
        admin,
        "PUT",
        "/api/admin/plugins/ai-work-assistant/config",
        json={"unknown_key": 1},
        expect=422,
        code="invalid_plugin_config",
    )
    req(
        admin,
        "PUT",
        "/api/admin/plugins/ai-work-assistant/enabled",
        json={"enabled": True},
    )

    actions = req(admin, "GET", "/api/plugins/actions").json()
    check(
        any(row["action_id"] == "ai-work-assistant.meeting_summary" for row in actions),
        "plugin actions list",
    )
    modules = req(admin, "GET", "/api/plugins/frontend-modules").json()
    check(modules["items"], "frontend modules")

    exported = req(
        admin,
        "POST",
        f"/api/meetings/{STATE['meeting_id']}/plugin-exports/meeting-export.markdown",
    )
    check("# 重构验收会（正式）" in exported.text, exported.text[:80])

    job = req(
        admin,
        "POST",
        "/api/plugin-jobs",
        json={
            "action_id": "ai-work-assistant.meeting_summary",
            "target_type": "meeting",
            "target_id": STATE["meeting_id"],
            "input": {"current_markdown": ""},
        },
        expect=201,
    ).json()
    terminal = None
    for _ in range(40):
        time.sleep(0.5)
        current = req(admin, "GET", f"/api/plugin-jobs/{job['id']}").json()
        if current["status"] in {"succeeded", "failed", "interrupted", "canceled"}:
            terminal = current
            break
    check(terminal is not None, "job never finished")
    check(
        terminal["status"] == "failed"
        and terminal["error_code"]
        in {
            "provider_network_error",
            "provider_http_error",
            "provider_timeout",
            "plugin_failed",
        },
        str(terminal),
    )
    req(
        admin,
        "POST",
        "/api/plugin-jobs",
        json={
            "action_id": "missing.action",
            "target_type": "meeting",
            "target_id": STATE["meeting_id"],
            "input": {},
        },
        expect=404,
        code="plugin_action_not_found",
    )
    jobs = req(admin, "GET", "/api/plugin-jobs").json()
    check(any(row["id"] == job["id"] for row in jobs["items"]), "jobs list")
    events = req(admin, "GET", "/api/admin/plugins/events").json()
    check(events["items"], "plugin events")
    return (
        "插件列表/配置/校验/动作/前端模块/导出/任务失败分类="
        f"{terminal['error_code']}/事件 OK"
    )


def s_permissions() -> str:
    admin = STATE["admin"]
    anna = STATE["anna"]
    ben = STATE["ben"]
    pid = STATE["project_id"]
    mid = STATE["meeting_id"]

    req(
        ben,
        "GET",
        f"/api/projects/{pid}",
        expect=403,
        code="project_view_forbidden",
    )
    meeting = req(ben, "GET", f"/api/meetings/{mid}")
    check(meeting.status_code == 200, "invited participant can view meeting")
    req(
        ben,
        "POST",
        f"/api/meetings/{mid}/agenda-items",
        params={"expected_meeting_version": meeting.json()["version"]},
        json={"title": "越权议题", "agenda_type": "discussion"},
        expect=403,
        code="project_contribution_forbidden",
    )
    req(
        ben,
        "GET",
        f"/api/projects/{pid}/activity",
        expect=403,
        code="project_view_forbidden",
    )
    check(req(anna, "GET", f"/api/projects/{pid}").status_code == 200, "member view")

    req(
        admin,
        "DELETE",
        f"/api/projects/{pid}",
        expect=409,
        code="project_not_empty",
    )
    empty = req(
        admin,
        "POST",
        "/api/projects",
        json={
            "name": "临时空项目",
            "slug": f"smoke-empty-{uuid.uuid4().hex[:6]}",
            "member_ids": [],
        },
        expect=201,
    ).json()
    req(admin, "DELETE", f"/api/projects/{empty['id']}", expect=204)
    return "非成员 403/受邀会议只读/成员可见/非空项目不可删/空项目可删 OK"


SECTIONS = [
    ("健康与就绪", s_infra),
    ("认证与账号管理", s_auth),
    ("项目与进展", s_projects),
    ("会议系列与周期实例", s_series),
    ("会议与议程操作", s_meeting_agenda),
    ("成果：决策/行动/问题", s_outcomes),
    ("评论与提及", s_comments),
    ("附件上传下载预览", s_attachments),
    ("会议详情投影", s_meeting_detail_shape),
    ("通知收件箱与 attention", s_inbox),
    ("完成快照/更正/重开/取消", s_lifecycle),
    ("工作区全局列表与简报", s_workspace),
    ("插件管理/动作/导出/任务", s_plugins),
    ("权限边界", s_permissions),
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="MeetFlow API smoke test")
    parser.add_argument(
        "--base-url",
        default=BASE,
        help="服务地址（默认 $MEETFLOW_BASE_URL 或 http://127.0.0.1:8000）",
    )
    parser.add_argument(
        "--admin-username",
        default=ADMIN_USER,
        help="管理员用户名（默认 $MEETFLOW_ADMIN_USERNAME 或 admin）",
    )
    parser.add_argument(
        "--admin-password",
        default=ADMIN_PASSWORD,
        help="管理员密码（默认 $MEETFLOW_ADMIN_PASSWORD）",
    )
    parser.add_argument(
        "--member-password",
        default=MEMBER_PASSWORD,
        help="脚本创建成员的密码（默认 $MEETFLOW_MEMBER_PASSWORD）",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    global BASE, ADMIN_USER, ADMIN_PASSWORD, MEMBER_PASSWORD
    BASE = args.base_url.rstrip("/")
    ADMIN_USER = args.admin_username
    ADMIN_PASSWORD = args.admin_password
    MEMBER_PASSWORD = args.member_password
    print(f"target: {BASE}\n")

    for name, fn in SECTIONS:
        try:
            detail = fn() or ""
            RESULTS.append((name, "PASS", detail))
        except Exception as exc:  # noqa: BLE001
            RESULTS.append((name, "FAIL", f"{type(exc).__name__}: {exc}"))

    width = max(len(name) for name, _, _ in RESULTS)
    failed = 0
    print("=" * 100)
    for name, status, detail in RESULTS:
        if status == "FAIL":
            failed += 1
        print(f"[{status}] {name.ljust(width)}  {detail}")
    print("=" * 100)
    print(f"{len(RESULTS) - failed}/{len(RESULTS)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
