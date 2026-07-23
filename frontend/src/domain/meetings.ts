import type { UserRef, Versioned } from '../api/contracts'
import type { ActionItem, Decision, OpenQuestion } from './outcomes'

export type MeetingStatus = 'draft' | 'ready' | 'in_progress' | 'completed' | 'canceled'
export type AgendaStatus = 'planned' | 'in_progress' | 'completed' | 'skipped' | 'canceled'
export type AgendaType = 'information' | 'discussion' | 'decision'
export type ParticipationRole = 'attendee' | 'host' | 'recorder' | 'presenter'

export type MeetingParticipant = {
  user: UserRef
  participation_role: ParticipationRole
  position: number
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
  decisions: Decision[]
  actions: ActionItem[]
  open_questions: OpenQuestion[]
  created_at: string
  updated_at: string
}

export type Meeting = Versioned & {
  id: string
  project: { id: string; name: string; slug: string }
  series: { id: string; title: string } | null
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
  created_by: UserRef
  updated_by: UserRef
  created_at: string
  updated_at: string
}
