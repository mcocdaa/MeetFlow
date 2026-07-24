import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import yaml
from pydantic import ValidationError
from jsonschema import ValidationError as JsonSchemaValidationError
from jsonschema import validate
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.models import UserRole
from app.database import Database
from app.plugins.contracts import (
    MeetingAction,
    PluginDescriptor,
    PluginLoadError,
    PluginManifest,
    PluginRegistry,
)
from app.plugins.models import PluginConfig, PluginState
from app.plugins.secrets import SecretBox


class ManifestError(ValueError):
    pass


class PluginInputError(ValueError):
    pass


class PluginOutputError(ValueError):
    pass


class PluginConfigurationError(ValueError):
    pass


class PluginManager:
    supported_api_version = 1

    def __init__(
        self, plugins_dir: Path, database: Database, app_secret_key: str
    ):
        self.plugins_dir = plugins_dir.resolve()
        self.database = database
        self.secret_box = SecretBox(app_secret_key)
        self._descriptors: dict[str, PluginDescriptor] = {}
        self._loaded_descriptors: dict[str, PluginDescriptor] = {}
        self._actions: dict[str, MeetingAction] = {}
        self._errors: list[PluginLoadError] = []
        self._modules: dict[str, ModuleType] = {}

    def errors(self) -> list[PluginLoadError]:
        return list(self._errors)

    def loaded_actions(self) -> list[MeetingAction]:
        return list(self._actions.values())

    def descriptors(self) -> list[PluginDescriptor]:
        return list(self._descriptors.values())

    def _record_error(self, plugin_id: str, exc: Exception) -> None:
        error_type = (
            "ManifestError" if isinstance(exc, ManifestError) else type(exc).__name__
        )
        error = PluginLoadError(
            plugin_id=plugin_id,
            error_type=error_type,
            message="插件清单无效"
            if error_type == "ManifestError"
            else "插件加载失败",
        )
        if not any(
            item.plugin_id == error.plugin_id
            and item.error_type == error.error_type
            for item in self._errors
        ):
            self._errors.append(error)

    def _resolve_plugin_dir(self, relative_path: str) -> Path:
        plugin_dir = (self.plugins_dir / relative_path).resolve()
        if self.plugins_dir not in plugin_dir.parents:
            raise ManifestError("plugin path escapes plugin root")
        return plugin_dir

    @staticmethod
    def _read_yaml(path: Path) -> dict:
        with path.open("r", encoding="utf-8") as stream:
            value = yaml.safe_load(stream) or {}
        if not isinstance(value, dict):
            raise ManifestError("YAML root must be a mapping")
        return value

    def discover(self) -> list[PluginDescriptor]:
        self._descriptors = {}
        registry_path = self.plugins_dir / "plugins.yaml"
        if not registry_path.exists():
            return []

        try:
            registry = self._read_yaml(registry_path)
        except Exception as exc:
            self._record_error("registry", exc)
            return []

        plugins = registry.get("plugins", {})
        if not isinstance(plugins, dict):
            self._record_error(
                "registry", ManifestError("plugins must be a mapping")
            )
            return []

        with self.database.session() as session:
            for plugin_id, config in plugins.items():
                try:
                    if not isinstance(config, dict):
                        raise ManifestError("plugin config must be a mapping")
                    plugin_dir = self._resolve_plugin_dir(
                        str(config.get("path", plugin_id))
                    )
                    manifest_path = plugin_dir / "plugin.yaml"
                    manifest = PluginManifest.model_validate(
                        self._read_yaml(manifest_path)
                    )
                    if manifest.id != plugin_id:
                        raise ManifestError("manifest id must match registry id")
                    if manifest.api_version != self.supported_api_version:
                        raise ManifestError("unsupported plugin API version")
                    entry_path = (plugin_dir / manifest.backend_entry).resolve()
                    if plugin_dir not in entry_path.parents:
                        raise ManifestError("backend entry escapes plugin directory")
                    if not entry_path.is_file():
                        raise ManifestError("backend entry does not exist")
                    state = session.get(PluginState, plugin_id)
                    enabled = (
                        state.enabled
                        if state is not None
                        else bool(config.get("enabled", False))
                    )
                    self._descriptors[plugin_id] = PluginDescriptor(
                        plugin_id=plugin_id,
                        path=plugin_dir,
                        manifest=manifest,
                        enabled=enabled,
                    )
                except (OSError, ValidationError, ManifestError) as exc:
                    if isinstance(exc, ValidationError):
                        exc = ManifestError("manifest schema validation failed")
                    self._record_error(str(plugin_id), exc)
        return self.descriptors()

    def _import_plugin(self, descriptor: PluginDescriptor) -> ModuleType:
        entry_path = (
            descriptor.path / descriptor.manifest.backend_entry
        ).resolve()
        module_name = f"meetflow_plugin_{descriptor.plugin_id.replace('-', '_')}"
        spec = importlib.util.spec_from_file_location(module_name, entry_path)
        if spec is None or spec.loader is None:
            raise ImportError("unable to create plugin module spec")
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        return module

    def load_enabled(self) -> None:
        self._errors = []
        self._actions = {}
        self._modules = {}
        self._loaded_descriptors = {}
        for descriptor in self.discover():
            if not descriptor.enabled:
                continue
            try:
                module = self._import_plugin(descriptor)
                register = getattr(module, "register", None)
                if not callable(register):
                    raise AttributeError("plugin must export register(registry)")
                registry = PluginRegistry(descriptor.plugin_id)
                register(registry)
                for action_id, action in registry.actions.items():
                    if action_id in self._actions:
                        raise ValueError("duplicate global action id")
                    self._actions[action_id] = action
                self._modules[descriptor.plugin_id] = module
                self._loaded_descriptors[descriptor.plugin_id] = descriptor
            except Exception as exc:
                self._record_error(descriptor.plugin_id, exc)

    def descriptor(self, plugin_id: str) -> PluginDescriptor | None:
        return self._descriptors.get(plugin_id)

    def _declared_fields(
        self, plugin_id: str, *, runtime: bool = False
    ) -> dict[str, bool]:
        descriptor = (
            self._loaded_descriptors.get(plugin_id)
            if runtime
            else self.descriptor(plugin_id)
        )
        if not descriptor:
            raise KeyError(plugin_id)
        declared: dict[str, bool] = {}
        for field in descriptor.manifest.config_schema.get("fields", []):
            declared[field.key] = False
        for field in descriptor.manifest.config_schema.get("secrets", []):
            declared[field.key] = True
        return declared

    def update_config(
        self,
        plugin_id: str,
        values: dict,
        actor_id: str,
        session: Session,
    ) -> dict:
        declared = self._declared_fields(plugin_id)
        unknown = set(values) - set(declared)
        if unknown:
            raise ValueError(f"unknown plugin config: {sorted(unknown)}")

        existing_rows = list(
            session.scalars(
                select(PluginConfig).where(
                    PluginConfig.plugin_id == plugin_id
                )
            )
        )
        for row in existing_rows:
            if row.config_key not in declared:
                session.delete(row)

        for key, value in values.items():
            row = session.scalar(
                select(PluginConfig).where(
                    PluginConfig.plugin_id == plugin_id,
                    PluginConfig.config_key == key,
                )
            )
            if value is None:
                if row:
                    session.delete(row)
                continue
            is_secret = declared[key]
            if is_secret and value == "":
                raise ValueError("secret value must not be empty")
            encoded = json.dumps(value, ensure_ascii=False)
            stored = self.secret_box.encrypt(encoded) if is_secret else encoded
            if row:
                row.stored_value = stored
                row.is_secret = is_secret
                row.updated_by = actor_id
            else:
                session.add(
                    PluginConfig(
                        plugin_id=plugin_id,
                        config_key=key,
                        stored_value=stored,
                        is_secret=is_secret,
                        updated_by=actor_id,
                    )
                )
        session.commit()
        return self.display_config(plugin_id, session)

    def display_config(self, plugin_id: str, session: Session) -> dict:
        declared = self._declared_fields(plugin_id)
        rows = session.scalars(
            select(PluginConfig).where(PluginConfig.plugin_id == plugin_id)
        )
        by_key = {row.config_key: row for row in rows}
        result: dict = {}
        for key, is_secret in declared.items():
            row = by_key.get(key)
            if is_secret:
                result[key] = {"configured": row is not None}
            elif row:
                result[key] = json.loads(row.stored_value)
            else:
                result[key] = None
        return result

    def runtime_config(self, plugin_id: str, session: Session) -> dict:
        descriptor = self._loaded_descriptors.get(plugin_id)
        if not descriptor:
            raise KeyError(plugin_id)
        declared = self._declared_fields(plugin_id, runtime=True)
        rows = session.scalars(
            select(PluginConfig).where(PluginConfig.plugin_id == plugin_id)
        )
        values: dict = {}
        for row in rows:
            if row.config_key not in declared:
                continue
            stored = (
                self.secret_box.decrypt(row.stored_value)
                if row.is_secret
                else row.stored_value
            )
            values[row.config_key] = json.loads(stored)

        required = [
            field.key
            for group in ("fields", "secrets")
            for field in descriptor.manifest.config_schema.get(group, [])
            if field.required
        ]
        missing = [key for key in required if key not in values]
        if missing:
            raise PluginConfigurationError(
                f"missing required config: {', '.join(missing)}"
            )
        return values

    def visible_actions(self, role: UserRole) -> list[dict]:
        return [
            {
                "action_id": action.action_id,
                "label": action.label,
                "description": action.description,
                "admin_only": action.admin_only,
                "input_schema": action.input_schema,
                "output_schema": action.output_schema,
                "target_types": action.target_types,
            }
            for action in self._actions.values()
            if not action.admin_only or role == UserRole.ADMIN
        ]

    async def invoke(
        self,
        action_id: str,
        context: dict,
        payload,
        session: Session,
    ) -> dict:
        action = self._actions.get(action_id)
        if not action:
            raise KeyError(action_id)
        try:
            validate(instance=payload, schema=action.input_schema)
        except JsonSchemaValidationError as exc:
            raise PluginInputError("plugin input schema rejected payload") from exc
        plugin_id = action_id.split(".", 1)[0]
        config = self.runtime_config(plugin_id, session)
        result = await action.handler(context, payload, config)
        try:
            validate(instance=result, schema=action.output_schema)
        except JsonSchemaValidationError as exc:
            raise PluginOutputError("plugin output schema rejected result") from exc
        return result
