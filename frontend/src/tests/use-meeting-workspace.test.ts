import { describe, expect, it, vi } from 'vitest'

import { useMeetingWorkspace } from '../composables/useMeetingWorkspace'

const meeting = {
  id: 'm1',
  title: 'Planning',
  purpose_markdown: '',
  raw_notes_markdown: '',
  summary_markdown: '',
  scheduled_start: '2026-07-24T02:00:00Z',
  scheduled_end: '2026-07-24T03:00:00Z',
  version: 1,
} as any

describe('useMeetingWorkspace', () => {
  it('persists the dirty draft with the meeting PUT and accepts the response', async () => {
    const request = vi.fn().mockResolvedValue({ ...meeting, raw_notes_markdown: 'new notes', version: 2 })
    const workspace = useMeetingWorkspace({ initial: meeting, request })

    workspace.draft.value.raw_notes_markdown = 'new notes'
    expect(await workspace.persistIfDirty()).toBe(true)

    expect(request).toHaveBeenCalledWith('/api/meetings/m1', expect.objectContaining({ method: 'PUT' }))
    expect(workspace.meeting.value?.version).toBe(2)
  })

  it('keeps the draft and exposes conflict when the server rejects its version', async () => {
    const request = vi.fn().mockRejectedValue({ status: 409, code: 'version_conflict' })
    const workspace = useMeetingWorkspace({ initial: meeting, request })

    workspace.draft.value.title = 'Local title'
    await expect(workspace.persistIfDirty()).rejects.toMatchObject({ status: 409 })

    expect(workspace.draft.value.title).toBe('Local title')
    expect(workspace.conflict.value).toBeTruthy()
    expect(workspace.saveState.value).toBe('conflict')
  })
})
