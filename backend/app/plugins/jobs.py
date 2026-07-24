import json
from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.models import User
from app.meetings.service import MeetingService
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
        if target_type != "meeting":
            raise ValueError("unsupported plugin target")
        action = next(
            (item for item in self.manager.loaded_actions() if item.action_id == action_id),
            None,
        )
        if action is None:
            raise KeyError(action_id)
        actor = self.session.get(User, actor_id)
        if actor is None:
            raise KeyError(actor_id)
        dedupe_key = f"{action_id}:{target_type}:{target_id}"
        existing = self.session.scalar(
            select(PluginJob).where(
                PluginJob.dedupe_key == dedupe_key,
                PluginJob.status.in_([PluginJobStatus.queued, PluginJobStatus.requesting]),
            )
        )
        if existing is not None:
            return existing, False
        context = self._json_snapshot(
            MeetingService(self.session).plugin_context(target_id, actor)
        )
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
        self.session.commit()
        self.session.refresh(job)
        return job, True

    @staticmethod
    def _json_snapshot(value: dict) -> dict:
        return json.loads(
            json.dumps(
                value,
                default=lambda item: item.isoformat()
                if isinstance(item, (date, datetime))
                else TypeError(f"unsupported plugin context value: {type(item)!r}"),
            )
        )
