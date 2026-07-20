from enum import StrEnum


class ProjectStatus(StrEnum):
    planned = "planned"
    active = "active"
    paused = "paused"
    completed = "completed"
    canceled = "canceled"


class ProjectHealth(StrEnum):
    on_track = "on_track"
    at_risk = "at_risk"
    off_track = "off_track"
    unset = "unset"


class ProjectMemberRole(StrEnum):
    member = "member"
    stakeholder = "stakeholder"


class ProjectUpdateSource(StrEnum):
    human = "human"
    ai_draft_applied = "ai_draft_applied"


class SeriesStatus(StrEnum):
    active = "active"
    archived = "archived"


class MeetingStatus(StrEnum):
    draft = "draft"
    ready = "ready"
    in_progress = "in_progress"
    completed = "completed"
    canceled = "canceled"


class ParticipationRole(StrEnum):
    attendee = "attendee"
    host = "host"
    recorder = "recorder"
    presenter = "presenter"


class AgendaType(StrEnum):
    information = "information"
    discussion = "discussion"
    decision = "decision"


class AgendaStatus(StrEnum):
    planned = "planned"
    in_progress = "in_progress"
    completed = "completed"
    skipped = "skipped"
    canceled = "canceled"


class DecisionStatus(StrEnum):
    proposed = "proposed"
    final = "final"
    superseded = "superseded"
    withdrawn = "withdrawn"


class DecisionReviewerStatus(StrEnum):
    pending = "pending"
    approved = "approved"
    changes_requested = "changes_requested"


class ActionPriority(StrEnum):
    low = "low"
    normal = "normal"
    high = "high"
    urgent = "urgent"


class ActionStatus(StrEnum):
    open = "open"
    in_progress = "in_progress"
    done = "done"
    canceled = "canceled"


class OpenQuestionStatus(StrEnum):
    open = "open"
    scheduled = "scheduled"
    resolved = "resolved"
    dropped = "dropped"
