import { fireEvent, render, screen, waitFor } from '@testing-library/vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import AgendaDetail from '../components/AgendaDetail.vue'
import AgendaQueue from '../components/AgendaQueue.vue'
import AgendaWorkbench from '../components/AgendaWorkbench.vue'

const { apiMock } = vi.hoisted(() => ({ apiMock: vi.fn() }))
vi.mock('../api/client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api/client')>()
  return { ...actual, api: apiMock }
})
vi.mock('../components/MarkdownEditor.vue', () => ({
  default: { props: ['modelValue', 'label'], emits: ['update:modelValue'], template: '<textarea :aria-label="label" :value="modelValue" @input="$emit(\'update:modelValue\', $event.target.value)" />' },
}))

const users = {
  lin: { id: 'u1', username: 'lin', display_name: '林宇' },
  qiao: { id: 'u2', username: 'qiao', display_name: '乔安' },
}

function meetingFixture() {
  const common = { meeting_id: 'm1', notes_markdown: '', proposer: null, presenter: null, estimated_minutes: 20, decisions: [], actions: [], open_questions: [], created_at: '', updated_at: '' }
  return {
    id: 'm1', project: { id: 'p1', name: 'MeetFlow', slug: 'meetflow' }, series: null, title: '迭代评审', purpose_markdown: '',
    scheduled_start: '2026-07-24T02:00:00Z', scheduled_end: '2026-07-24T03:00:00Z', status: 'in_progress' as const,
    host: users.lin, recorder: users.qiao, summary_markdown: '', raw_notes_markdown: '', version: 4,
    participants: [{ user: users.lin, participation_role: 'host' as const, position: 0 }, { user: users.qiao, participation_role: 'recorder' as const, position: 1 }],
    agenda_items: [
      { ...common, id: 'a1', title: '进展同步', agenda_type: 'information' as const, status: 'in_progress' as const, position: 0, version: 2 },
      { ...common, id: 'a2', title: '发布方案', agenda_type: 'decision' as const, status: 'planned' as const, position: 1, version: 1 },
    ],
    created_by: users.lin, updated_by: users.lin, created_at: '', updated_at: '',
  }
}

describe('agenda workbench', () => {
  beforeEach(() => {
    apiMock.mockReset()
    apiMock.mockResolvedValue({})
  })

  it('keeps detail left and the narrow queue right', () => {
    render(AgendaWorkbench, { props: { meeting: meetingFixture() } })
    const detail = screen.getByTestId('agenda-detail')
    const queue = screen.getByTestId('agenda-queue')
    expect(detail.compareDocumentPosition(queue) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    expect(queue).toHaveClass('agenda-queue-narrow')
  })

  it('sends the full ordered id list once after drop', async () => {
    render(AgendaQueue, { props: { meeting: meetingFixture() } })
    await fireEvent.dragStart(screen.getByTestId('agenda-row-a2'))
    await fireEvent.drop(screen.getByTestId('agenda-row-a1'))
    await waitFor(() => expect(apiMock).toHaveBeenCalledTimes(1))
    expect(apiMock).toHaveBeenCalledWith('/api/meetings/m1/agenda-items/reorder', {
      method: 'POST',
      body: JSON.stringify({ ids: ['a2', 'a1'], expected_meeting_version: 4 }),
    })
  })

  it('keeps outcome creation separate from meeting flow commands', () => {
    render(AgendaDetail, { props: { meeting: meetingFixture(), item: meetingFixture().agenda_items[0] } })
    expect(screen.getByTestId('outcome-actions')).toHaveTextContent('+ 决策')
    expect(screen.getByTestId('flow-actions')).toHaveTextContent('完成并进入下一项')
    expect(screen.getByTestId('outcome-actions')).not.toContainElement(screen.getByRole('button', { name: '完成并进入下一项' }))
  })

  it('shows a useful guard when an agenda with outcomes cannot be deleted', async () => {
    const { ApiError } = await import('../api/client')
    apiMock.mockRejectedValueOnce(new ApiError(409, 'agenda_has_outcomes', '议题已有产出，不能直接删除'))
    render(AgendaQueue, { props: { meeting: meetingFixture() } })
    await fireEvent.click(screen.getByRole('button', { name: '议题“进展同步”的更多操作' }))
    await fireEvent.click(screen.getByRole('button', { name: '删除议题' }))
    expect(await screen.findByText('议题已有产出，请先迁移产出，或将议题标记为取消。')).toBeVisible()
    expect(screen.getByRole('button', { name: '改为取消' })).toBeVisible()
  })
})
