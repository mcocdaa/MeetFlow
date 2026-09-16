import type { UserRef, Versioned } from '../api/contracts'

export type MeetingComment = Versioned & {
  id: string
  parent_id?: string | null
  body_markdown: string | null
  creator: UserRef
  mentions?: UserRef[]
  edited_at?: string | null
  deleted_at?: string | null
  created_at?: string
  updated_at?: string
  replies: MeetingComment[]
  /** The API does not expose a reply total; `reply_next_cursor` is the authoritative "more replies" signal. */
  reply_count?: number
  reply_next_cursor?: string | null
  resolved_at: string | null
  resolved_by: UserRef | null
  can_edit: boolean
  can_delete?: boolean
  can_resolve: boolean
}

export type CommentPage = {
  items: MeetingComment[]
  next_cursor: string | null
}
