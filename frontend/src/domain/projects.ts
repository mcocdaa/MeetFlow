import type { UserRef, Versioned } from '../api/contracts'

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
