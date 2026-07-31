import { api } from './client'
import type { Meeting } from '../domain/meetings'

export type LifecycleAction = 'start' | 'finish'

export type MeetingUpdate = {
  expected_version: number
  title: string
  purpose_markdown: string
  raw_notes_markdown: string
  summary_markdown: string
  scheduled_start: string
  scheduled_end: string
}

export function getMeeting(id: string) {
  return api<Meeting>(`/api/meetings/${id}`)
}

export function updateMeeting(id: string, body: MeetingUpdate) {
  return api<Meeting>(`/api/meetings/${id}`, {
    method: 'PUT',
    body: JSON.stringify(body),
  })
}

export function runMeetingLifecycle(id: string, action: LifecycleAction, expectedVersion: number) {
  return api<Meeting>(`/api/meetings/${id}/${action}`, {
    method: 'POST',
    body: JSON.stringify({ expected_version: expectedVersion }),
  })
}
