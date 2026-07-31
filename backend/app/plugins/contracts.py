from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from app.auth.models import User
    from app.plugins.models import PluginJob


class ConfigField(BaseModel):
    key: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    type: str
    required: bool = False


class PluginCapabilities(BaseModel):
    model_config = ConfigDict(extra="forbid")

    actions: list[str] = Field(default_factory=list)
    exporters: list[str] = Field(default_factory=list)
    event_subscriptions: list[str] = Field(default_factory=list)
    ui_slots: list[str] = Field(default_factory=list)
    context_scopes: list[str] = Field(default_factory=list)
    external_network: bool = False


class PluginManifest(BaseModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9-]*$")
    name: str
    version: str
    api_version: int
    backend_entry: str = "backend.py"
    frontend_entry: str | None = Field(default=None, max_length=240)
    description: str = ""
    config_schema: dict[str, list[ConfigField]] = Field(default_factory=dict)
    capabilities: PluginCapabilities = Field(default_factory=PluginCapabilities)


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
StreamHandler = Callable[
    [dict[str, Any], dict[str, Any], dict[str, Any]],
    AsyncIterator[str],
]
ApplyHandler = Callable[
    ["PluginJob", dict[str, Any], "User", "Session"], dict[str, Any]
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
    stream_handler: StreamHandler | None = None
    apply_handler: ApplyHandler | None = None
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
