import type { UserRef, Versioned } from '../api/contracts'

export type MeetingComment = Versioned & {
  id: string
  body_markdown: string | null
  creator: UserRef
  replies: MeetingComment[]
  resolved_at: string | null
  resolved_by: UserRef | null
  can_edit: boolean
  can_resolve: boolean
}

export type CommentPage = {
  items: MeetingComment[]
  next_cursor: string | null
}
