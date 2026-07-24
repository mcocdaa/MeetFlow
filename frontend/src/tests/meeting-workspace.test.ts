import { fireEvent, render, screen } from '@testing-library/vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { apiMock } = vi.hoisted(() => ({ apiMock: vi.fn() }))
vi.mock('../api/client', () => ({ api: apiMock, ApiError: class ApiError extends Error {} }))
vi.mock('vue-router', () => ({ useRoute: () => ({ params: { id: 'm1' } }) }))
vi.mock('../components/MarkdownEditor.vue', () => ({ default: { template: '<textarea />' } }))

import MeetingWorkspaceView from '../views/MeetingWorkspaceView.vue'

const user = { id: 'u1', username: 'lin', display_name: '林宇' }
const meeting = {
  id: 'm1', project: { id: 'p1', name: 'MeetFlow', slug: 'meetflow' }, series: null, title: '迭代评审', purpose_markdown: '', scheduled_start: '2026-07-24T02:00:00Z', scheduled_end: '2026-07-24T03:00:00Z', status: 'ready', host: user, recorder: user, summary_markdown: '', raw_notes_markdown: '', version: 2,
  participants: [{ user, participation_role: 'host', position: 0 }],
  agenda_items: [{ id: 'a1', meeting_id: 'm1', title: '发布方案', agenda_type: 'decision', notes_markdown: '', status: 'planned', position: 0, proposer: null, presenter: null, estimated_minutes: 20, decisions: [], actions: [], open_questions: [], version: 1, created_at: '', updated_at: '' }],
  attachments: [], created_by: user, updated_by: user, created_at: '', updated_at: '',
} as any

describe('meeting workspace', () => {
  beforeEach(() => { apiMock.mockReset(); apiMock.mockResolvedValue(meeting) })

  it('keeps preparation fields on demand instead of above the active agenda', async () => {
    render(MeetingWorkspaceView)
    await screen.findByText('Current topic')
    const preparation = screen.getByRole('button', { name: '准备信息' })
    expect(screen.queryByRole('heading', { name: '会议准备' })).not.toBeInTheDocument()
    await fireEvent.click(preparation)
    expect(screen.getByRole('dialog', { name: '准备信息' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: '会议准备' })).toBeInTheDocument()
  })

  it('places summary and action AI drafts in the meeting work surface', async () => {
    render(MeetingWorkspaceView)
    await screen.findByText('Current topic')
    expect(screen.getByTestId('meeting-inline-summary')).toBeInTheDocument()
    expect(screen.getByTestId('meeting-inline-actions')).toBeInTheDocument()
  })
})
