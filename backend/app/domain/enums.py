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
