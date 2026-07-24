import json
from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth.models import User
from app.meetings.schemas import MeetingEdit
from app.meetings.service import MeetingService
from app.projects.schemas import ProjectUpdateWrite
from app.projects.service import ProjectService
from app.plugins.context import PluginContextBuilder
from app.plugins.manager import PluginManager
from app.plugins.models import PluginJob, PluginJobStatus


class PluginJobService:
    def __init__(self, session: Session, manager: PluginManager):
        self.session = session
        self.manager = manager

    def submit(
        self,
        action_id: str,
        target_type: str,
        target_id: str,
        input_json: dict,
        actor_id: str,
    ) -> tuple[PluginJob, bool]:
        action = next(
            (item for item in self.manager.loaded_actions() if item.action_id == action_id),
            None,
        )
        if action is None:
            raise KeyError(action_id)
        if target_type not in action.target_types:
            raise ValueError("unsupported plugin target")
        actor = self.session.get(User, actor_id)
        if actor is None:
            raise KeyError(actor_id)
        dedupe_key = f"{action_id}:{target_type}:{target_id}"
        context_builder = PluginContextBuilder(self.session)
        if target_type == "meeting":
            context = context_builder.meeting(target_id, actor)
        elif target_type == "project":
            context = context_builder.project(target_id, actor)
        else:
            raise ValueError("unsupported plugin target")
        context = self._json_snapshot(context)
        job = PluginJob(
            plugin_id=action_id.split(".", 1)[0],
            action_id=action_id,
            target_type=target_type,
            target_id=target_id,
            dedupe_key=dedupe_key,
            input_json=input_json,
            context_snapshot=context,
            created_by=actor_id,
        )
        self.session.add(job)
        try:
            self.session.commit()
        except IntegrityError:
            self.session.rollback()
            existing = self.session.scalar(
                select(PluginJob).where(
                    PluginJob.dedupe_key == dedupe_key,
                    PluginJob.status.in_(
                        [PluginJobStatus.queued, PluginJobStatus.requesting]
                    ),
                )
            )
            if existing is None:
                raise
            return existing, False
        self.session.refresh(job)
        return job, True

    def cancel(self, job: PluginJob) -> PluginJob:
        if job.status != PluginJobStatus.queued:
            raise ValueError("only queued jobs can be canceled")
        job.status = PluginJobStatus.canceled
        job.finished_at = datetime.now().astimezone()
        self.session.commit()
        self.session.refresh(job)
        return job

    def rerun(self, job: PluginJob, actor_id: str) -> PluginJob:
        if job.status not in {
            PluginJobStatus.succeeded,
            PluginJobStatus.failed,
            PluginJobStatus.interrupted,
            PluginJobStatus.canceled,
        }:
            raise ValueError("only terminal jobs can be rerun")
        rerun, created = self.submit(
            job.action_id,
            job.target_type,
            job.target_id,
            job.input_json,
            actor_id,
        )
        if created:
            rerun.rerun_of_id = job.id
            self.session.commit()
            self.session.refresh(rerun)
        return rerun

    def apply_meeting_summary(
        self,
        job: PluginJob,
        edited_markdown: str,
        expected_version: int,
        actor: User,
    ) -> dict:
        if job.action_id != "ai-work-assistant.meeting_summary":
            raise ValueError("job does not produce a meeting summary")
        if job.status != PluginJobStatus.succeeded:
            raise ValueError("only succeeded jobs can be applied")
        if job.applied_at is not None:
            raise ValueError("job was already applied")
        meeting = MeetingService(self.session).update_meeting(
            job.target_id,
            MeetingEdit(
                expected_version=expected_version,
                summary_markdown=edited_markdown,
            ),
            actor,
        )
        job = self.session.get(PluginJob, job.id)
        if job is None or job.applied_at is not None:
            raise ValueError("job was already applied")
        job.applied_by = actor.id
        job.applied_at = datetime.now().astimezone()
        self.session.commit()
        return MeetingService(self.session).serialize_meeting(meeting)

    def apply_project_progress(
        self, job: PluginJob, edited_markdown: str, actor: User
    ) -> dict:
        if job.action_id != "ai-work-assistant.project_progress":
            raise ValueError("job does not produce a project progress update")
        if job.status != PluginJobStatus.succeeded:
            raise ValueError("only succeeded jobs can be applied")
        if job.applied_at is not None:
            raise ValueError("job was already applied")
        update = ProjectService(self.session).create_update(
            job.target_id,
            ProjectUpdateWrite(
                content_markdown=edited_markdown,
                source="ai_draft_applied",
            ),
            actor,
        )
        job = self.session.get(PluginJob, job.id)
        if job is None or job.applied_at is not None:
            raise ValueError("job was already applied")
        job.applied_by = actor.id
        job.applied_at = datetime.now().astimezone()
        self.session.commit()
        return ProjectService(self.session).serialize_update(update)

    @staticmethod
    def _json_snapshot(value: dict) -> dict:
        def json_default(item: object) -> str:
            if isinstance(item, (date, datetime)):
                return item.isoformat()
            raise TypeError(f"unsupported plugin context value: {type(item)!r}")

        return json.loads(
            json.dumps(
                value,
                default=json_default,
            )
        )
