import pytest

from app.domain.enums import MeetingStatus
from app.errors import AppError
from app.meetings.policies import LifecyclePolicy


def test_lifecycle_policy_accepts_draft_and_ready_for_start():
    assert LifecyclePolicy.can_start(MeetingStatus.draft)
    assert LifecyclePolicy.can_start(MeetingStatus.ready)
    assert not LifecyclePolicy.can_start(MeetingStatus.completed)


def test_lifecycle_policy_rejects_finish_outside_in_progress():
    with pytest.raises(AppError) as error:
        LifecyclePolicy.require(
            MeetingStatus.ready,
            MeetingStatus.completed,
            LifecyclePolicy.can_finish(MeetingStatus.ready),
        )

    assert error.value.code == "invalid_state_transition"
    assert error.value.details == {"from": "ready", "to": "completed"}
