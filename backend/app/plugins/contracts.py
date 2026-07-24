from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class ConfigField(BaseModel):
    key: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    type: str
    required: bool = False


class PluginManifest(BaseModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9-]*$")
    name: str
    version: str
    api_version: int
    backend_entry: str = "backend.py"
    description: str = ""
    config_schema: dict[str, list[ConfigField]] = Field(default_factory=dict)


class PluginLoadError(BaseModel):
    plugin_id: str
    error_type: str
    message: str


@dataclass
class PluginDescriptor:
    plugin_id: str
    path: Path
    manifest: PluginManifest
    enabled: bool


Handler = Callable[
    [dict[str, Any], dict[str, Any], dict[str, Any]],
    Awaitable[dict[str, Any]],
]


@dataclass
class MeetingAction:
    action_id: str
    label: str
    description: str
    admin_only: bool
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    handler: Handler
    target_types: tuple[str, ...] = ("meeting",)


@dataclass
class PluginRegistry:
    plugin_id: str
    actions: dict[str, MeetingAction] = field(default_factory=dict)

    def register_meeting_action(self, action: MeetingAction) -> None:
        if not action.action_id.startswith(f"{self.plugin_id}."):
            raise ValueError("action_id must be prefixed by plugin id")
        if action.action_id in self.actions:
            raise ValueError("duplicate action_id")
        self.actions[action.action_id] = action
