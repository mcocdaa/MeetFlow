import json
from typing import Any

from app.plugins.contracts import PluginExport, PluginRegistry


def _text(value: Any) -> str:
    return "" if value is None else str(value)


def _markdown(context: dict[str, Any]) -> bytes:
    lines = [f"# {_text(context.get('title'))}"]
    project = context.get("project")
    if project:
        lines.append(f"\n项目：{_text(project)}")
    if context.get("scheduled_start"):
        lines.append(f"时间：{_text(context['scheduled_start'])}")
    if context.get("summary_markdown"):
        lines.extend(["\n## 会议纪要", _text(context["summary_markdown"])])
    if context.get("purpose_markdown"):
        lines.extend(["\n## 会议目的", _text(context["purpose_markdown"])])

    lines.append("\n## 议程")
    for index, item in enumerate(context.get("agenda_items", []), start=1):
        lines.append(f"{index}. **{_text(item.get('title'))}**（{_text(item.get('status'))}）")
        if item.get("notes_markdown"):
            lines.append(f"   {item['notes_markdown']}")
    return ("\n".join(lines).rstrip() + "\n").encode("utf-8")


async def export_markdown(context: dict[str, Any], _config: dict[str, Any]) -> PluginExport:
    return PluginExport(
        media_type="text/markdown; charset=utf-8",
        filename="meeting.md",
        content=_markdown(context),
    )


async def export_json(context: dict[str, Any], _config: dict[str, Any]) -> PluginExport:
    return PluginExport(
        media_type="application/json; charset=utf-8",
        filename="meeting.json",
        content=(json.dumps(context, ensure_ascii=False, indent=2, default=str) + "\n").encode(
            "utf-8"
        ),
    )


def register(registry: PluginRegistry) -> None:
    registry.register_exporter("meeting-export.markdown", export_markdown)
    registry.register_exporter("meeting-export.json", export_json)
