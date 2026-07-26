import asyncio
import logging
from typing import Any, Literal

from fastapi import (
    APIRouter,
    Body,
    Depends,
    HTTPException,
    Request,
    Response,
    status,
)
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
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
from app.plugins.jobs import PluginJobService
from app.plugins.models import PluginJob, PluginJobStatus

admin_router = APIRouter(prefix="/api/admin/plugins", tags=["admin/plugins"])
actions_router = APIRouter(prefix="/api/plugins", tags=["plugins"])
meeting_actions_router = APIRouter(prefix="/api/meetings", tags=["plugins"])
jobs_router = APIRouter(prefix="/api/plugin-jobs", tags=["plugins"])
logger = logging.getLogger(__name__)


class EnabledRequest(BaseModel):
    enabled: bool


class JobSubmitRequest(BaseModel):
    action_id: str = Field(min_length=3, max_length=160)
    target_type: str = Field(min_length=3, max_length=40)
    target_id: str = Field(min_length=1, max_length=36)
    input: dict[str, Any] = Field(default_factory=dict)


def serialize_job(job: PluginJob) -> dict[str, Any]:
    return {
        "id": job.id,
        "plugin_id": job.plugin_id,
        "action_id": job.action_id,
        "target_type": job.target_type,
        "target_id": job.target_id,
        "status": job.status,
        "result": job.result_json,
        "error_code": job.error_code,
        "error_message": job.error_message,
        "error_detail": job.error_detail,
        "rerun_of_id": job.rerun_of_id,
        "applied_by": job.applied_by,
        "applied_at": job.applied_at,
        "dismissed_by": job.dismissed_by,
        "dismissed_at": job.dismissed_at,
        "created_at": job.created_at,
        "started_at": job.started_at,
        "finished_at": job.finished_at,
    }


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


@actions_router.get("/frontend-modules")
def list_frontend_modules(
    request: Request, _user: User = Depends(current_user)
) -> dict[str, list[dict[str, str]]]:
    return {"items": request.app.state.plugin_manager.frontend_modules()}


@actions_router.get("/{plugin_id}/frontend/{asset_path:path}")
def get_frontend_asset(
    plugin_id: str,
    asset_path: str,
    request: Request,
    _user: User = Depends(current_user),
) -> FileResponse:
    asset = request.app.state.plugin_manager.frontend_asset(plugin_id, asset_path)
    if asset is None:
        raise HTTPException(status_code=404)
    return FileResponse(asset)


@jobs_router.post("", status_code=status.HTTP_201_CREATED)
def submit_job(
    payload: JobSubmitRequest,
    request: Request,
    response: Response,
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
):
    try:
        job, created = PluginJobService(
            session, request.app.state.plugin_manager
        ).submit(
            payload.action_id,
            payload.target_type,
            payload.target_id,
            payload.input,
            user.id,
        )
    except KeyError as exc:
        raise AppError(404, "plugin_action_not_found", "插件动作不存在") from exc
    except ValueError as exc:
        raise AppError(422, "invalid_plugin_target", "插件目标无效") from exc
    if not created:
        response.status_code = status.HTTP_200_OK
    return serialize_job(job)


@jobs_router.get("/{job_id}")
def get_job(
    job_id: str,
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    job = session.get(PluginJob, job_id)
    if job is None:
        raise AppError(404, "plugin_job_not_found", "AI 任务不存在")
    if job.created_by != user.id and user.role.value != "admin":
        raise AppError(403, "plugin_job_forbidden", "无权查看此 AI 任务")
    return serialize_job(job)


def get_accessible_job(session: Session, job_id: str, user: User) -> PluginJob:
    job = session.get(PluginJob, job_id)
    if job is None:
        raise AppError(404, "plugin_job_not_found", "AI 任务不存在")
    if job.created_by != user.id and user.role.value != "admin":
        raise AppError(403, "plugin_job_forbidden", "无权操作此 AI 任务")
    return job


@jobs_router.post("/{job_id}/cancel")
def cancel_job(
    job_id: str,
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    job = get_accessible_job(session, job_id, user)
    try:
        return serialize_job(PluginJobService(session, None).cancel(job))
    except ValueError as exc:
        raise AppError(409, "plugin_job_not_cancelable", "当前 AI 任务无法取消") from exc


@jobs_router.post("/{job_id}/dismiss")
def dismiss_job(
    job_id: str,
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    job = get_accessible_job(session, job_id, user)
    try:
        return serialize_job(PluginJobService(session, None).dismiss(job, user.id))
    except ValueError as exc:
        raise AppError(409, "plugin_job_not_dismissible", "当前 AI 草稿无法丢弃") from exc


@jobs_router.post("/{job_id}/rerun", status_code=status.HTTP_201_CREATED)
def rerun_job(
    job_id: str,
    request: Request,
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    job = get_accessible_job(session, job_id, user)
    try:
        rerun = PluginJobService(session, request.app.state.plugin_manager).rerun(
            job, user.id
        )
    except ValueError as exc:
        raise AppError(409, "plugin_job_not_rerunnable", "当前 AI 任务无法重新运行") from exc
    return serialize_job(rerun)


@jobs_router.post("/{job_id}/apply")
def apply_job(
    job_id: str,
    request: Request,
    payload: dict[str, Any] = Body(default_factory=dict),
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    job = get_accessible_job(session, job_id, user)
    try:
        return request.app.state.plugin_manager.apply(job, payload, user, session)
    except ValueError as exc:
        raise AppError(409, "plugin_job_not_applicable", "当前 AI 草稿无法应用") from exc


@jobs_router.get("")
def list_jobs(
    target_type: Literal["meeting", "project"] | None = None,
    target_id: str | None = None,
    include_history: bool = False,
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    if (target_type is None) != (target_id is None):
        raise AppError(422, "invalid_plugin_target_filter", "任务筛选参数不完整")
    statement = select(PluginJob).where(PluginJob.created_by == user.id)
    if target_type is not None:
        statement = statement.where(
            PluginJob.target_type == target_type, PluginJob.target_id == target_id
        )
    if not include_history:
        statement = statement.where(
            PluginJob.applied_at.is_(None), PluginJob.dismissed_at.is_(None)
        )
    jobs = session.scalars(statement.order_by(PluginJob.created_at.desc(), PluginJob.id.desc()))
    return {"items": [serialize_job(job) for job in jobs]}


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
