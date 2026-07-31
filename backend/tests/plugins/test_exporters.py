import asyncio
import importlib.util
from pathlib import Path

import pytest

from app.plugins.exporters import PluginExport, validate_export


EXPORTER_PATH = Path(__file__).resolve().parents[3] / "plugins" / "meeting-export" / "backend.py"
_spec = importlib.util.spec_from_file_location("meeting_export_backend", EXPORTER_PATH)
assert _spec is not None and _spec.loader is not None
meeting_export = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(meeting_export)


def test_validate_export_accepts_bounded_binary_result():
    result = validate_export(
        PluginExport(
            media_type="text/markdown",
            filename="meeting.md",
            content=b"# Meeting",
        )
    )

    assert result.filename == "meeting.md"
    assert result.content == b"# Meeting"


@pytest.mark.parametrize(
    "result",
    [
        PluginExport(media_type="", filename="meeting.md", content=b"x"),
        PluginExport(media_type="text/plain", filename="../secret.txt", content=b"x"),
        PluginExport(media_type="text/plain", filename="meeting.txt", content="text"),  # type: ignore[arg-type]
    ],
)
def test_validate_export_rejects_unsafe_result(result):
    with pytest.raises(ValueError):
        validate_export(result)


def test_validate_export_rejects_results_over_eight_megabytes():
    with pytest.raises(ValueError, match="8 MB"):
        validate_export(
            PluginExport(
                media_type="application/octet-stream",
                filename="large.bin",
                content=b"x" * (8 * 1024 * 1024 + 1),
            )
        )


def test_meeting_exporter_only_serializes_bounded_context():
    context = {
        "title": "Planning",
        "project": "MeetFlow",
        "summary_markdown": "Decision summary",
        "agenda_items": [{"title": "Current topic", "status": "completed"}],
    }

    result = asyncio.run(meeting_export.export_markdown(context, {}))

    assert result.media_type.startswith("text/markdown")
    assert result.filename == "meeting.md"
    assert b"Current topic" in result.content
    assert b"database-password" not in result.content
