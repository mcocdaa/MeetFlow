export type PersonRef = { id?: string; username?: string; display_name: string }

export type MeetingWrite = {
  title: string
  project: string
  meeting_type: string
  meeting_date: string
  participants: string[]
  raw_notes_markdown: string
  conclusions_markdown: string
}

export type ActionStatus = 'open' | 'done'
export type ActionItem = {
  id: string
  meeting_id: string
  meeting_title?: string
  content: string
  owner: string
  due_date: string | null
  status: ActionStatus
  created_by: PersonRef
  created_at: string
  updated_at: string
}

export type Attachment = {
  id: string
  meeting_id: string
  original_name: string
  mime_type: string
  size: number
  attachment_type: 'image' | 'file'
  created_by: PersonRef
  created_at: string
}

export type MeetingUpdate = {
  id: string
  meeting_id: string
  content_markdown: string
  created_by: PersonRef
  created_at: string
}

export type MeetingSummary = {
  id: string
  title: string
  project: string
  meeting_type: string
  meeting_date: string
  participants: string[]
  conclusion_count: number
  action_count?: number
  open_action_count: number
  attachment_count: number
  created_by: PersonRef
  updated_by: PersonRef
  updated_at?: string
}

export type MeetingPackage = MeetingWrite & {
  id: string
  actions: ActionItem[]
  attachments: Attachment[]
  updates: MeetingUpdate[]
  created_by: PersonRef
  updated_by: PersonRef
  created_at: string
  updated_at: string
}
