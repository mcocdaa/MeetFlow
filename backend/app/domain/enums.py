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
