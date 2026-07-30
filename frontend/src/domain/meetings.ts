import type { UserRef, Versioned } from '../api/contracts'
import type { ActionItem, Decision, OpenQuestion } from './outcomes'

export type MeetingStatus = 'draft' | 'ready' | 'in_progress' | 'completed' | 'canceled'
export type AgendaStatus = 'planned' | 'in_progress' | 'completed' | 'skipped' | 'canceled'
export type AgendaType = 'information' | 'discussion' | 'decision'
export type ParticipationRole = 'attendee' | 'host' | 'recorder' | 'presenter'
export type OccurrenceKind = 'scheduled' | 'manual'
export type RecurrenceFrequency = 'daily' | 'weekly' | 'monthly' | 'yearly'

export type MeetingSeriesRecurrence = {
  frequency: RecurrenceFrequency | null
  interval: number
  weekday: number | null
  month_day: number | null
  month: number | null
  local_time: string | null
  timezone: string | null
  anchor_date: string | null
}

export type MeetingSeries = Versioned & {
  id: string
  project: { id: string; name: string; slug: string }
  title: string
  purpose_markdown: string
  recurrence_description: string
  recurrence: MeetingSeriesRecurrence
  default_duration_minutes: number
  status: string
}

export type AgendaDraft = {
  title: string
  agenda_type: AgendaType
  notes_markdown: string
  estimated_minutes: number | null
}

export type MeetingParticipant = {
  user: UserRef
  participation_role: ParticipationRole
  position: number
}

export type Attachment = {
  id: string
  target_type: 'project' | 'meeting' | 'agenda_item'
  target_id: string
  original_name: string
  mime_type: string
  size: number
  attachment_type: 'image' | 'file'
  created_by: UserRef
  created_at: string
  download_url: string
  preview_url?: string
}

export type MeetingAmendment = {
  id: string
  meeting_id: string
  reason: string
  content_markdown: string
  created_by: UserRef
  created_at: string
}

export type MeetingSnapshot = {
  id: string
  completion_number: number
  snapshot_json?: Record<string, any>
  snapshot?: Record<string, any>
  created_by: UserRef
  created_at: string
}

export type AgendaItem = Versioned & {
  id: string
  meeting_id: string
  title: string
  agenda_type: AgendaType
  notes_markdown: string
  status: AgendaStatus
  position: number
  proposer: UserRef | null
  presenter: UserRef | null
  estimated_minutes: number | null
  actual_duration_seconds?: number | null
  decisions: Decision[]
  actions: ActionItem[]
  open_questions: OpenQuestion[]
  attachments?: Attachment[]
  created_at: string
  updated_at: string
}

export type Meeting = Versioned & {
  id: string
  project: { id: string; name: string; slug: string }
  series: { id: string; title: string } | null
  occurrence_kind?: OccurrenceKind
  series_slot_at?: string | null
  title: string
  purpose_markdown: string
  scheduled_start: string
  scheduled_end: string
  status: MeetingStatus
  host: UserRef | null
  recorder: UserRef | null
  summary_markdown: string
  raw_notes_markdown: string
  participants: MeetingParticipant[]
  agenda_items: AgendaItem[]
  meeting_decisions?: Decision[]
  meeting_actions?: ActionItem[]
  meeting_open_questions?: OpenQuestion[]
  attachments?: Attachment[]
  amendments?: MeetingAmendment[]
  snapshots?: MeetingSnapshot[]
  current_snapshot?: MeetingSnapshot | null
  created_by: UserRef
  updated_by: UserRef
  created_at: string
  updated_at: string
}
