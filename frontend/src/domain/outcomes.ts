import type { UserRef, Versioned } from '../api/contracts'

export type DecisionStatus = 'proposed' | 'final' | 'superseded' | 'withdrawn'
export type ActionStatus = 'open' | 'in_progress' | 'done' | 'canceled'
export type ActionPriority = 'low' | 'normal' | 'high' | 'urgent'
export type OpenQuestionStatus = 'open' | 'scheduled' | 'resolved' | 'dropped'

export type Decision = Versioned & {
  id: string
  project_id: string
  meeting_id: string | null
  agenda_item_id: string | null
  title: string
  decision_markdown: string
  rationale_markdown: string
  status: DecisionStatus
  is_derived?: boolean
  created_by: UserRef
  created_at: string
  updated_at: string
}

export type ActionItem = Versioned & {
  id: string
  project_id: string
  meeting_id: string | null
  agenda_item_id: string | null
  content: string
  owner: UserRef | null
  due_date: string | null
  priority: ActionPriority
  status: ActionStatus
  is_derived?: boolean
  created_by: UserRef
  created_at: string
  updated_at: string
  completed_at: string | null
}

export type OpenQuestion = Versioned & {
  id: string
  project_id: string
  meeting_id: string | null
  agenda_item_id: string | null
  question_markdown: string
  owner: UserRef | null
  status: OpenQuestionStatus
  is_derived?: boolean
  created_by: UserRef
  created_at: string
  updated_at: string
}
