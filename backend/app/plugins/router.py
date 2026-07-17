import asyncio
import logging
from typing import Any

from fastapi import APIRouter, Body, Depends, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth.dependencies import admin_user, current_user
from app.auth.models import User
from app.database import get_session
from app.errors import AppError
from app.meetings.service import MeetingService
from app.plugins.manager import (
    PluginConfigurationError,
    PluginInputError,
    PluginOutputError,
)
from app.plugins.models import PluginState

admin_router = APIRouter(prefix="/api/admin/plugins", tags=["admin/plugins"])
actions_router = APIRouter(prefix="/api/plugins", tags=["plugins"])
meeting_actions_router = APIRouter(prefix="/api/meetings", tags=["plugins"])
logger = logging.getLogger(__name__)


class EnabledRequest(BaseModel):
    enabled: bool


@admin_router.get("")
def list_plugins(
    request: Request,
    _admin: User = Depends(admin_user),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    manager = request.app.state.plugin_manager
    manager.discover()
    plugins = []
    for descriptor in manager.descriptors():
        plugins.append(
            {
                "id": descriptor.plugin_id,
                "name": descriptor.manifest.name,
                "version": descriptor.manifest.version,
                "description": descriptor.manifest.description,
                "enabled": descriptor.enabled,
                "config_schema": {
                    key: [field.model_dump() for field in fields]
                    for key, fields in descriptor.manifest.config_schema.items()
                },
                "config": manager.display_config(
                    descriptor.plugin_id, session
                ),
            }
        )
    return {
        "plugins": plugins,
        "errors": [error.model_dump() for error in manager.errors()],
    }


@admin_router.put("/{plugin_id}/config")
def update_plugin_config(
    plugin_id: str,
    payload: dict[str, Any],
    request: Request,
    admin: User = Depends(admin_user),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    manager = request.app.state.plugin_manager
    if not manager.descriptor(plugin_id):
        manager.discover()
    try:
        return manager.update_config(plugin_id, payload, admin.id, session)
    except KeyError as exc:
        raise AppError(404, "plugin_not_found", "插件不存在") from exc
    except ValueError as exc:
        raise AppError(422, "invalid_plugin_config", "插件配置无效") from exc


@admin_router.put("/{plugin_id}/enabled")
def update_plugin_enabled(
    plugin_id: str,
    payload: EnabledRequest,
    request: Request,
    admin: User = Depends(admin_user),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    manager = request.app.state.plugin_manager
    if not manager.descriptor(plugin_id):
        manager.discover()
    if not manager.descriptor(plugin_id):
        raise AppError(404, "plugin_not_found", "插件不存在")
    state = session.get(PluginState, plugin_id)
    if state:
        state.enabled = payload.enabled
        state.updated_by = admin.id
    else:
        session.add(
            PluginState(
                plugin_id=plugin_id,
                enabled=payload.enabled,
                updated_by=admin.id,
            )
        )
    session.commit()
    return {"enabled": payload.enabled, "restart_required": True}


@actions_router.get("/actions")
def list_actions(
    request: Request, user: User = Depends(current_user)
) -> list[dict]:
    return request.app.state.plugin_manager.visible_actions(user.role)


@meeting_actions_router.post("/{meeting_id}/plugin-actions/{action_id}")
async def run_action(
    meeting_id: str,
    action_id: str,
    request: Request,
    payload: Any = Body(...),
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> dict:
    manager = request.app.state.plugin_manager
    action = next(
        (
            item
            for item in manager.loaded_actions()
            if item.action_id == action_id
        ),
        None,
    )
    if not action:
        raise AppError(404, "plugin_action_not_found", "插件动作不存在")
    if action.admin_only and user.role.value != "admin":
        raise AppError(403, "admin_required", "需要管理员权限")
    context = MeetingService(session).plugin_context(meeting_id, user)
    try:
        return await asyncio.wait_for(
            manager.invoke(action_id, context, payload, session),
            timeout=request.app.state.settings.plugin_timeout_seconds,
        )
    except PluginInputError as exc:
        raise AppError(422, "invalid_action_payload", "插件输入无效") from exc
    except PluginConfigurationError as exc:
        raise AppError(409, "plugin_not_configured", "插件配置不完整") from exc
    except PluginOutputError as exc:
        logger.error(
            "Plugin action failed plugin_id=%s action_id=%s error_type=%s",
            action_id.split(".", 1)[0],
            action_id,
            type(exc).__name__,
        )
        raise AppError(502, "plugin_invalid_output", "插件返回格式无效") from exc
    except TimeoutError as exc:
        logger.error(
            "Plugin action failed plugin_id=%s action_id=%s error_type=%s",
            action_id.split(".", 1)[0],
            action_id,
            type(exc).__name__,
        )
        raise AppError(504, "plugin_timeout", "插件执行超时") from exc
    except Exception as exc:
        logger.error(
            "Plugin action failed plugin_id=%s action_id=%s error_type=%s",
            action_id.split(".", 1)[0],
            action_id,
            type(exc).__name__,
        )
        raise AppError(502, "plugin_failed", "插件执行失败") from exc
