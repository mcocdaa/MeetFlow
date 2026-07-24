import type { UserRef, Versioned } from '../api/contracts'
import type { Decision } from './outcomes'

export type ProjectStatus = 'planned' | 'active' | 'paused' | 'completed' | 'canceled'
export type ProjectHealth = 'on_track' | 'at_risk' | 'off_track' | 'unset'
export type ProjectMemberRole = 'member' | 'stakeholder'

export type ProjectMembership = {
  role: ProjectMemberRole
  user: UserRef
}

export type ProjectUpdate = {
  id: string
  project_id: string
  health: ProjectHealth
  content_markdown: string
  source: 'human' | 'ai_draft_applied'
  created_by: UserRef
  created_at: string
  updated_at: string
}

export type Project = Versioned & {
  id: string
  name: string
  slug: string
  summary: string
  description_markdown: string
  status: ProjectStatus
  health: ProjectHealth
  lead: UserRef | null
  target_date: string | null
  memberships: ProjectMembership[]
  updates: ProjectUpdate[]
  created_by: UserRef
  updated_by: UserRef
  created_at: string
  updated_at: string
}

export type ProjectAttachment = {
  id: string
  target_type: 'project' | 'meeting' | 'agenda_item'
  target_id: string
  original_name: string
  mime_type: string
  size: number
  attachment_type: 'image' | 'file'
  download_url: string
  created_by: UserRef
  created_at: string
}

export type ProjectActionSummary = {
  id: string
  content: string
  status: string
  priority: string
  owner_user_id: string | null
  due_date: string | null
  meeting_id: string | null
}

export type ProjectDetail = Project & {
  next_meeting: { id: string; title: string; scheduled_start: string; status: string } | null
  recent_decisions: Decision[]
  meeting_count: number
  decision_count: number
  open_action_count: number
  series_summaries: { id: string; title: string; status: string; recurrence_description: string }[]
  attachments: ProjectAttachment[]
}
