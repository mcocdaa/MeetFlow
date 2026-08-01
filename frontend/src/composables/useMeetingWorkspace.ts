import { computed, getCurrentInstance, onBeforeUnmount, ref, watch } from 'vue'

import { api, ApiError } from '../api/client'
import type { MeetingUpdate } from '../api/meetings'
import type { Meeting } from '../domain/meetings'

export type MeetingDraft = {
  title: string
  purpose_markdown: string
  raw_notes_markdown: string
  summary_markdown: string
  scheduled_start: string
  scheduled_end: string
}

export type SaveState = 'idle' | 'saving' | 'saved' | 'error' | 'conflict'
type Requester = <T = unknown>(path: string, init?: RequestInit) => Promise<T>

function toLocalInput(value: string) {
  const date = new Date(value)
  const local = new Date(date.getTime() - date.getTimezoneOffset() * 60_000)
  return local.toISOString().slice(0, 16)
}

export function draftFor(value: Meeting): MeetingDraft {
  return {
    title: value.title,
    purpose_markdown: value.purpose_markdown,
    raw_notes_markdown: value.raw_notes_markdown,
    summary_markdown: value.summary_markdown,
    scheduled_start: toLocalInput(value.scheduled_start),
    scheduled_end: toLocalInput(value.scheduled_end),
  }
}

export function useMeetingWorkspace(options: {
  initial?: Meeting
  request?: Requester
  debounceMs?: number
  autoSave?: boolean
} = {}) {
  const request = options.request ?? api
  const debounceMs = options.debounceMs ?? 800
  const meeting = ref<Meeting | null>(options.initial ?? null)
  const initialDraft = options.initial ? draftFor(options.initial) : {
    title: '', purpose_markdown: '', raw_notes_markdown: '', summary_markdown: '', scheduled_start: '', scheduled_end: '',
  }
  const draft = ref<MeetingDraft>({ ...initialDraft })
  const acceptedDraft = ref<MeetingDraft>({ ...initialDraft })
  const saving = ref(false)
  const saveState = ref<SaveState>('idle')
  const conflict = ref<unknown | null>(null)
  let saveTimer: ReturnType<typeof setTimeout> | undefined

  const dirty = computed(() => JSON.stringify(draft.value) !== JSON.stringify(acceptedDraft.value))

  function accept(value: Meeting, resetDraft = true) {
    meeting.value = value
    if (!resetDraft) return
    const next = draftFor(value)
    draft.value = next
    acceptedDraft.value = { ...next }
    conflict.value = null
    saveState.value = 'idle'
  }

  function updatePayload(): MeetingUpdate {
    if (!meeting.value) throw new Error('meeting_not_loaded')
    return {
      expected_version: meeting.value.version,
      ...draft.value,
      scheduled_start: new Date(draft.value.scheduled_start).toISOString(),
      scheduled_end: new Date(draft.value.scheduled_end).toISOString(),
    }
  }

  async function persistIfDirty(): Promise<boolean> {
    if (!meeting.value || !dirty.value) return false
    if (saveTimer) clearTimeout(saveTimer)
    saving.value = true
    saveState.value = 'saving'
    try {
      const value = await request<Meeting>(`/api/meetings/${meeting.value.id}`, {
        method: 'PUT',
        body: JSON.stringify(updatePayload()),
      })
      accept(value)
      saveState.value = 'saved'
      return true
    } catch (caught) {
      conflict.value = caught
      const isConflict = caught instanceof ApiError
        ? caught.status === 409
        : Boolean(caught && typeof caught === 'object' && ('status' in caught || 'code' in caught)
          && ((caught as { status?: number }).status === 409 || (caught as { code?: string }).code === 'version_conflict'))
      saveState.value = isConflict ? 'conflict' : 'error'
      throw caught
    } finally {
      saving.value = false
    }
  }

  function scheduleSave() {
    if (!meeting.value || !dirty.value) return
    if (saveTimer) clearTimeout(saveTimer)
    saveTimer = setTimeout(() => {
      saveTimer = undefined
      void persistIfDirty().catch(() => undefined)
    }, debounceMs)
  }

  if (options.autoSave !== false) watch(draft, scheduleSave, { deep: true })
  if (getCurrentInstance()) {
    onBeforeUnmount(() => { if (saveTimer) clearTimeout(saveTimer) })
  }

  return {
    meeting,
    draft,
    acceptedDraft,
    saving,
    saveState,
    conflict,
    dirty,
    accept,
    persistIfDirty,
    scheduleSave,
  }
}
