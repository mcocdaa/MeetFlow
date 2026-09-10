from __future__ import annotations

from app.domain.enums import MeetingStatus
from app.errors import AppError


#: Statuses in which a meeting's content (agenda, notes, outcomes) may change.
MUTABLE_MEETING_STATUSES = {
    MeetingStatus.draft,
    MeetingStatus.ready,
    MeetingStatus.in_progress,
}


class LifecyclePolicy:
    """Pure state-transition rules shared by HTTP and future non-HTTP callers."""

    @staticmethod
    def can_start(status: MeetingStatus) -> bool:
        return status in {MeetingStatus.draft, MeetingStatus.ready}

    @staticmethod
    def can_finish(status: MeetingStatus) -> bool:
        return status == MeetingStatus.in_progress

    @staticmethod
    def require(status: MeetingStatus, target: MeetingStatus, allowed: bool) -> None:
        if allowed:
            return
        raise AppError(
            409,
            "invalid_state_transition",
            "会议状态不可执行此操作",
            details={"from": status.value, "to": target.value},
        )

    @staticmethod
    def require_mutable_status(status: MeetingStatus) -> None:
        """Raise the agenda-specific lock error for non-mutable statuses."""
        if status == MeetingStatus.completed:
            raise AppError(409, "meeting_completed", "已完成的会议不可修改")
        if status not in MUTABLE_MEETING_STATUSES:
            raise AppError(409, "meeting_immutable", "当前会议状态不可修改议程")
