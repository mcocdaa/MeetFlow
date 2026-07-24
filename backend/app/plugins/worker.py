import asyncio

from sqlalchemy import select, update

from app.database import Database
from app.meetings.models import utcnow
from app.plugins.manager import PluginManager
from app.plugins.models import PluginJob, PluginJobStatus


class PluginJobWorker:
    def __init__(self, database: Database, manager: PluginManager):
        self.database = database
        self.manager = manager
        self._stop = asyncio.Event()

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
            session.commit()

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
        except Exception:
            with self.database.session() as session:
                job = session.get(PluginJob, job_id)
                if job is not None and job.status == PluginJobStatus.requesting:
                    job.status = PluginJobStatus.failed
                    job.error_code = "plugin_failed"
                    job.error_message = "AI 任务执行失败"
                    job.finished_at = utcnow()
                    session.commit()
        return True

    async def serve(self) -> None:
        while not self._stop.is_set():
            if not await self.run_once():
                try:
                    await asyncio.wait_for(self._stop.wait(), timeout=1)
                except TimeoutError:
                    pass

    def stop(self) -> None:
        self._stop.set()
