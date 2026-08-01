from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePath


MAX_EXPORT_BYTES = 8 * 1024 * 1024


@dataclass(frozen=True)
class PluginExport:
    media_type: str
    filename: str
    content: bytes


def validate_export(result: PluginExport) -> PluginExport:
    if not result.media_type.strip():
        raise ValueError("export media type must not be empty")
    if not isinstance(result.content, bytes):
        raise ValueError("export content must be bytes")
    if "\\" in result.filename or any(
        ord(character) < 32 or ord(character) == 127
        for character in result.filename
    ):
        raise ValueError("export filename must be a single safe path segment")
    path = PurePath(result.filename)
    if not result.filename or path.name != result.filename or result.filename in {".", ".."}:
        raise ValueError("export filename must be a single safe path segment")
    if len(result.content) > MAX_EXPORT_BYTES:
        raise ValueError("export content exceeds 8 MB")
    return result
