import asyncio
import re
from dataclasses import dataclass
from datetime import timedelta

import httpx
from sqlalchemy import or_, select, update

from app.database import Database
from app.meetings.models import utcnow
from app.plugins.manager import (
    PluginConfigurationError,
    PluginInputError,
    PluginManager,
    PluginOutputError,
)
from app.plugins.models import (
    PluginEvent,
    PluginEventStatus,
    PluginJob,
    PluginJobStatus,
)


@dataclass(frozen=True)
class ExecutionDiagnostic:
    code: str
    message: str
    detail: str


def _redact_detail(value: str) -> str:
    redacted = re.sub(r"(?i)(bearer\s+)[^\s,;]+", r"\1[redacted]", value)
    redacted = re.sub(
        r"(?i)([\"']?api[_-]?key[\"']?\s*[=:]\s*[\"']?)[^\s,;\"']+",
        r"\1[redacted]",
        redacted,
    )
    redacted = re.sub(r"\bsk-[A-Za-z0-9_-]{8,}\b", "[redacted]", redacted)
    return redacted[:800]


def _provider_detail(exc: httpx.HTTPStatusError) -> str:
    response = exc.response
    parts = [f"HTTP {response.status_code}"]
    if response.reason_phrase:
        parts.append(response.reason_phrase)
    body = response.text.strip()
    if body:
        parts.append(body)
    return _redact_detail(" · ".join(parts))


def classify_execution_error(exc: Exception) -> ExecutionDiagnostic:
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        code_and_message = {
            401: (
                "provider_auth_failed",
                "认证或权限失败；检查管理员插件设置中的 API Key、服务地址和权限。",
            ),
            403: (
                "provider_auth_failed",
                "认证或权限失败；检查管理员插件设置中的 API Key、服务地址和权限。",
            ),
            402: (
                "provider_insufficient_balance",
                "AI 服务额度不足；请充值或更换有可用额度的 API Key。",
            ),
            404: (
                "provider_not_found",
                "找不到 AI 服务或模型；检查服务地址和模型名称。",
            ),
            408: (
                "provider_timeout",
                "AI 服务响应超时；请稍后重试或检查超时设置。",
            ),
            429: (
                "provider_rate_limited",
                "AI 服务限流或配额已用尽；请稍后重试并检查服务额度。",
            ),
        }
        code, message = code_and_message.get(
            status,
            ("provider_http_error", "AI 服务返回 HTTP 状态错误。"),
        )
        return ExecutionDiagnostic(code, message, _provider_detail(exc))
    if isinstance(exc, httpx.TimeoutException):
        return ExecutionDiagnostic(
            "provider_timeout",
            "AI 服务响应超时；请稍后重试或检查超时设置。",
            _redact_detail(f"{type(exc).__name__}: {exc}"),
        )
    if isinstance(exc, httpx.RequestError):
        return ExecutionDiagnostic(
            "provider_network_error",
            "无法连接 AI 服务；检查服务地址和网络。",
            _redact_detail(f"{type(exc).__name__}: {exc}"),
        )
    if isinstance(exc, PluginConfigurationError):
        return ExecutionDiagnostic(
            "plugin_not_configured",
            "AI 插件配置不完整；请联系管理员检查插件设置。",
            _redact_detail(f"{type(exc).__name__}: {exc}"),
        )
    if isinstance(exc, PluginInputError):
        return ExecutionDiagnostic(
            "plugin_input_invalid",
            "AI 任务输入不符合插件要求。",
            _redact_detail(f"{type(exc).__name__}: {exc}"),
        )
    if isinstance(exc, PluginOutputError):
        return ExecutionDiagnostic(
            "plugin_output_invalid",
            "AI 服务返回内容与插件格式不兼容。",
            _redact_detail(f"{type(exc).__name__}: {exc}"),
        )
    return ExecutionDiagnostic(
        "plugin_failed",
        "AI 任务执行失败；请查看技术详情或联系管理员。",
        _redact_detail(f"{type(exc).__name__}: {exc}"),
    )


class PluginJobWorker:
    max_event_attempts = 5

    def __init__(self, database: Database, manager: PluginManager):
        self.database = database
        self.manager = manager
        self._stop = asyncio.Event()
        self._running = False

    @property
    def running(self) -> bool:
        return self._running

    def recover(self) -> None:
        with self.database.session() as session:
            session.execute(
                update(PluginJob)
                .where(PluginJob.status == PluginJobStatus.requesting)
                .values(
                    status=PluginJobStatus.interrupted,
                    error_code="process_restarted",
                    error_message="服务重启，未重复发送 AI 请求",
                    finished_at=utcnow(),
                )
            )
            session.execute(
                update(PluginEvent)
                .where(PluginEvent.status == PluginEventStatus.processing)
                .values(
                    status=PluginEventStatus.queued,
                    claimed_at=None,
                    next_attempt_at=utcnow(),
                    last_error="服务重启，事件重新排队",
                )
            )
            session.commit()

    async def run_event_once(self) -> bool:
        now = utcnow()
        with self.database.session() as session:
            event = session.scalar(
                select(PluginEvent)
                .where(
                    PluginEvent.status == PluginEventStatus.queued,
                    or_(
                        PluginEvent.next_attempt_at.is_(None),
                        PluginEvent.next_attempt_at <= now,
                    ),
                )
                .order_by(PluginEvent.created_at, PluginEvent.event_id)
                .limit(1)
            )
            if event is None:
                return False
            event.status = PluginEventStatus.processing
            event.claimed_at = now
            event.attempts += 1
            session.commit()
            event_id = event.event_id
            event_type = event.event_type
            payload = event.payload_json

        try:
            with self.database.session() as session:
                await self.manager.invoke_event(event_type, payload, session)
                event = session.get(PluginEvent, event_id)
                if event is not None and event.status == PluginEventStatus.processing:
                    event.status = PluginEventStatus.succeeded
                    event.finished_at = utcnow()
                    event.last_error = None
                    session.commit()
        except Exception as exc:
            diagnostic = classify_execution_error(exc)
            with self.database.session() as session:
                event = session.get(PluginEvent, event_id)
                if event is not None and event.status == PluginEventStatus.processing:
                    if event.attempts >= self.max_event_attempts:
                        event.status = PluginEventStatus.failed
                        event.finished_at = utcnow()
                    else:
                        event.status = PluginEventStatus.queued
                        event.next_attempt_at = utcnow() + timedelta(
                            seconds=min(2 ** (event.attempts - 1) * 5, 300)
                        )
                    event.last_error = _redact_detail(
                        diagnostic.detail or diagnostic.message
                    )
                    session.commit()
        return True

    async def run_once(self) -> bool:
        with self.database.session() as session:
            job = session.scalar(
                select(PluginJob)
                .where(PluginJob.status == PluginJobStatus.queued)
                .order_by(PluginJob.created_at, PluginJob.id)
                .limit(1)
            )
            if job is None:
                return False
            job.status = PluginJobStatus.requesting
            job.started_at = utcnow()
            session.commit()
            job_id = job.id
            action_id = job.action_id
            context = job.context_snapshot
            payload = job.input_json
        try:
            with self.database.session() as session:
                result = await self.manager.invoke(action_id, context, payload, session)
                job = session.get(PluginJob, job_id)
                if job is not None and job.status == PluginJobStatus.requesting:
                    job.status = PluginJobStatus.succeeded
                    job.result_json = result
                    job.finished_at = utcnow()
                    session.commit()
        except Exception as exc:
            diagnostic = classify_execution_error(exc)
            with self.database.session() as session:
                job = session.get(PluginJob, job_id)
                if job is not None and job.status == PluginJobStatus.requesting:
                    job.status = PluginJobStatus.failed
                    job.error_code = diagnostic.code
                    job.error_message = diagnostic.message
                    job.error_detail = diagnostic.detail
                    job.finished_at = utcnow()
                    session.commit()
        return True

    async def serve(self) -> None:
        self._running = True
        try:
            while not self._stop.is_set():
                did_work = await self.run_event_once()
                if not did_work:
                    did_work = await self.run_once()
                if not did_work:
                    try:
                        await asyncio.wait_for(self._stop.wait(), timeout=1)
                    except TimeoutError:
                        pass
        finally:
            self._running = False

    def stop(self) -> None:
        self._stop.set()
