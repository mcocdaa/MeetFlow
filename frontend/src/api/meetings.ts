import { api, apiDownload } from './client'
import type { Meeting, MeetingParticipantWrite } from '../domain/meetings'

export type LifecycleAction = 'start' | 'finish' | 'cancel' | 'reopen'

export type MeetingUpdate = {
  expected_version: number
  title: string
  purpose_markdown: string
  raw_notes_markdown: string
  summary_markdown: string
  scheduled_start: string
  scheduled_end: string
  host_user_id?: string | null
  recorder_user_id?: string | null
  participants?: MeetingParticipantWrite[]
}

export function getMeeting(id: string) {
  return api<Meeting>(`/api/meetings/${id}`)
}

export function runMeetingLifecycle(id: string, action: LifecycleAction, expectedVersion: number) {
  return api<Meeting>(`/api/meetings/${id}/${action}`, {
    method: 'POST',
    body: JSON.stringify({ expected_version: expectedVersion }),
  })
}

export function downloadMeetingExport(id: string, exporterId: string) {
  return apiDownload(`/api/meetings/${id}/plugin-exports/${encodeURIComponent(exporterId)}`, { method: 'POST' })
}

export type MeetingIngestPayload = {
  agenda_title?: string
  agenda_item_id?: string | number | null
  notes_markdown: string
  auto_complete_agenda?: boolean
}

export type MeetingIngestResponse = Meeting & {
  meeting?: Meeting
  ingested_agenda_item_id: string
  decisions: number
  actions: number
  questions: number
  extracted: {
    decisions: number
    actions: number
    questions: number
  }
}

export type ApiKeyInfo = {
  api_key: string
  token_prefix: string
  user_id: string
  username: string
}

export function ingestMeetingNotes(id: string, payload: MeetingIngestPayload) {
  return api<MeetingIngestResponse>(`/api/v1/meetings/${id}/ingest`, {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function fetchApiKey() {
  return api<ApiKeyInfo>('/api/v1/auth/api-key')
}

export function rotateApiKey() {
  return api<ApiKeyInfo>('/api/v1/auth/api-key/rotate', {
    method: 'POST',
  })
}
