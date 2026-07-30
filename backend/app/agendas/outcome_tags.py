from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from app.errors import AppError


OutcomeKind = Literal["decision", "action", "question"]


@dataclass(frozen=True)
class TaggedOutcome:
    kind: OutcomeKind
    content: str
    source_tag_key: str


_TAGS: tuple[tuple[OutcomeKind, str], ...] = (
    ("decision", "@决策:"),
    ("action", "@行动:"),
    ("question", "@开放问题:"),
)


def parse_outcome_tags(markdown: str) -> list[TaggedOutcome]:
    """Parse the only three supported, one-per-line agenda outcome tags."""
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
        content = line[len(prefix) :].strip()
        if not content or any(tag in content for _, tag in _TAGS):
            raise AppError(
                422,
                "invalid_agenda_outcome_tag",
                "议题成果标签必须每行填写一项非空内容",
                details={"line": line_number},
            )
        source_tag_key = f"{kind}:{counters[kind]}"
        counters[kind] += 1
        result.append(
            TaggedOutcome(
                kind=kind,
                content=content,
                source_tag_key=source_tag_key,
            )
        )
    return result
