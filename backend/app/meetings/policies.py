from __future__ import annotations

from app.domain.enums import MeetingStatus
from app.errors import AppError


class LifecyclePolicy:
    """Pure state-transition rules shared by HTTP and future non-HTTP callers."""

    @staticmethod
    def can_start(status: MeetingStatus) -> bool:
        return status in {MeetingStatus.draft, MeetingStatus.ready}

    @staticmethod
    def can_finish(status: MeetingStatus) -> bool:
        return status == MeetingStatus.in_progress

    @staticmethod
    def can_cancel(status: MeetingStatus) -> bool:
        return status in {
            MeetingStatus.draft,
            MeetingStatus.ready,
            MeetingStatus.in_progress,
        }

    @staticmethod
    def can_reopen(status: MeetingStatus) -> bool:
        return status == MeetingStatus.completed

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
