from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from typing import Literal

from app.domain.enums import ActionStatus
from app.errors import AppError


OutcomeKind = Literal["decision", "action", "question"]

_BRACKET_RE = re.compile(r"^\[([^\]]+)\]")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


@dataclass(frozen=True)
class TaggedOutcome:
    kind: OutcomeKind
    content: str
    source_tag_key: str
    status: ActionStatus = ActionStatus.open
    owner_name: str | None = None
    due_date: date | None = None


_TAGS: tuple[tuple[OutcomeKind, str], ...] = (
    ("decision", "@决策:"),
    ("action", "@行动:"),
    ("question", "@开放问题:"),
)


def parse_action_metadata(
    raw_payload: str,
) -> tuple[str, ActionStatus, str | None, date | None]:
    """Parse [status][@owner][due_date] from the beginning of raw action content."""
    text = raw_payload.strip()
    status = ActionStatus.open
    owner: str | None = None
    due_date_val: date | None = None

    while True:
        text = text.strip()
        match = _BRACKET_RE.match(text)
        if not match:
            break
        token = match.group(1).strip()
        text = text[match.end() :]

        if token.startswith("@"):
            owner = token[1:].strip()
        elif _DATE_RE.match(token):
            try:
                due_date_val = date.fromisoformat(token)
            except ValueError:
                pass
        elif token.lower() in ("todo", "open"):
            status = ActionStatus.open
        elif token.lower() in ("in_progress", "doing", "progress"):
            status = ActionStatus.in_progress
        elif token.lower() in ("done", "completed", "finish", "finished"):
            status = ActionStatus.done
        elif token.lower() in ("canceled", "cancelled"):
            status = ActionStatus.canceled

    return text.strip(), status, owner, due_date_val


def format_action_tag(
    *,
    content: str,
    status: ActionStatus | str = ActionStatus.open,
    owner: str | None = None,
    due_date: date | str | None = None,
) -> str:
    """Format an ActionItem into the tag syntax @行动:[status][@owner][due_date] content."""
    status_str = status.value if hasattr(status, "value") else str(status)
    status_token = (
        "done"
        if status_str == "done"
        else (
            "in_progress"
            if status_str == "in_progress"
            else ("canceled" if status_str == "canceled" else "todo")
        )
    )
    parts = [f"[{status_token}]"]
    if owner:
        clean_owner = owner.lstrip("@").strip()
        if clean_owner:
            parts.append(f"[@{clean_owner}]")
    if due_date:
        due_str = due_date.isoformat() if hasattr(due_date, "isoformat") else str(due_date).strip()
        if due_str:
            parts.append(f"[{due_str}]")
    return f"@行动:{''.join(parts)} {content.strip()}"


def rewrite_action_in_notes(
    notes_markdown: str,
    source_tag_key: str,
    new_tag_line: str,
) -> str:
    """Rewrite the line corresponding to source_tag_key in notes_markdown."""
    try:
        target_index = int(source_tag_key.split(":", 1)[1])
    except (IndexError, ValueError):
        return notes_markdown

    lines = notes_markdown.splitlines(keepends=True)
    action_count = 0
    for idx, raw_line in enumerate(lines):
        line = raw_line.strip()
        if line.startswith("@行动:"):
            if action_count == target_index:
                leading_ws_len = len(raw_line) - len(raw_line.lstrip())
                leading = raw_line[:leading_ws_len]
                ending = "\n" if raw_line.endswith("\n") else ""
                lines[idx] = f"{leading}{new_tag_line}{ending}"
                return "".join(lines)
            action_count += 1
    return notes_markdown


def parse_outcome_tags(markdown: str) -> list[TaggedOutcome]:
    """Parse the supported, one-per-line agenda outcome tags."""
    counters: dict[OutcomeKind, int] = {
        "decision": 0,
        "action": 0,
        "question": 0,
    }
    result: list[TaggedOutcome] = []
    for line_number, raw_line in enumerate(markdown.splitlines(), start=1):
        line = raw_line.strip()
        matched = next(
            ((kind, prefix) for kind, prefix in _TAGS if line.startswith(prefix)),
            None,
        )
        if matched is None:
            continue
        kind, prefix = matched
        raw_payload = line[len(prefix) :].strip()
        if not raw_payload or any(tag in raw_payload for _, tag in _TAGS):
            raise AppError(
                422,
                "invalid_agenda_outcome_tag",
                "议题成果标签必须每行填写一项非空内容",
                details={"line": line_number},
            )

        status = ActionStatus.open
        owner_name = None
        due_date_val = None
        if kind == "action":
            content, status, owner_name, due_date_val = parse_action_metadata(raw_payload)
            if not content or any(tag in content for _, tag in _TAGS):
                raise AppError(
                    422,
                    "invalid_agenda_outcome_tag",
                    "议题成果标签必须每行填写一项非空内容",
                    details={"line": line_number},
                )
        else:
            content = raw_payload

        source_tag_key = f"{kind}:{counters[kind]}"
        counters[kind] += 1
        result.append(
            TaggedOutcome(
                kind=kind,
                content=content,
                source_tag_key=source_tag_key,
                status=status,
                owner_name=owner_name,
                due_date=due_date_val,
            )
        )
    return result

