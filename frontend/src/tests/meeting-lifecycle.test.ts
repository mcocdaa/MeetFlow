import { fireEvent, render, screen, waitFor } from '@testing-library/vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import MeetingWorkspaceView from '../views/MeetingWorkspaceView.vue'

const { apiMock } = vi.hoisted(() => ({ apiMock: vi.fn() }))
vi.mock('../api/client', async (importOriginal) => ({ ...await importOriginal<typeof import('../api/client')>(), api: apiMock }))
vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { id: 'm1' } }),
  RouterLink: { props: ['to'], template: '<a :href="to"><slot /></a>' },
}))
vi.mock('../components/MarkdownEditor.vue', () => ({
  default: { props: ['modelValue', 'label'], emits: ['update:modelValue'], template: '<textarea :aria-label="label" :value="modelValue" @input="$emit(\'update:modelValue\', $event.target.value)" />' },
}))

const user = { id: 'u1', username: 'lin', display_name: '林宇' }
function fixture(status: 'draft' | 'ready' | 'in_progress' | 'completed', unresolved = 0) {
  const agenda = Array.from({ length: Math.max(unresolved, 1) }, (_, index) => ({
    id: `a${index + 1}`, meeting_id: 'm1', title: index ? `待处理议题 ${index + 1}` : '发布方案', agenda_type: 'decision',
    notes_markdown: '', status: unresolved ? (index ? 'planned' : 'in_progress') : 'completed', position: index, proposer: null, presenter: null,
    estimated_minutes: 20, decisions: [], actions: [], open_questions: [], version: 1, created_at: '', updated_at: '', attachments: [],
  }))
  return {
    id: 'm1', project: { id: 'p1', name: 'MeetFlow', slug: 'meetflow' }, series: null, title: '迭代评审', purpose_markdown: '确认发布范围',
    scheduled_start: '2026-07-24T02:00:00Z', scheduled_end: '2026-07-24T03:00:00Z', status, host: user, recorder: user,
    summary_markdown: '本轮范围已经确认', raw_notes_markdown: '', version: 4, participants: [{ user, participation_role: 'host', position: 0 }],
    agenda_items: agenda, meeting_decisions: [], meeting_actions: [], meeting_open_questions: [], attachments: [], amendments: [], snapshots: [],
    current_snapshot: status === 'completed' ? { id: 's1', completion_number: 1, snapshot_json: { meeting: { title: '迭代评审', summary_markdown: '本轮范围已经确认' }, agenda_items: agenda }, created_by: user, created_at: '' } : null,
    created_by: user, updated_by: user, created_at: '', updated_at: '',
  }
}

describe('meeting lifecycle workspace', () => {
  beforeEach(() => apiMock.mockReset())

  it.each([
    ['draft', '准备会议'],
    ['in_progress', '完成议题并进入下一项'],
    ['completed', '添加更正'],
  ] as const)('renders %s meeting controls', async (status, control) => {
    apiMock.mockResolvedValue(fixture(status, status === 'in_progress' ? 1 : 0))
    render(MeetingWorkspaceView)
    await waitFor(() => expect(apiMock).toHaveBeenCalledWith('/api/meetings/m1'))
    expect(await screen.findByText(control, { selector: status === 'draft' ? 'span' : undefined })).toBeVisible()
  })

  it('weakens finish while unresolved agenda remains', async () => {
    apiMock.mockResolvedValue(fixture('in_progress', 2))
    render(MeetingWorkspaceView)
    expect(await screen.findByRole('button', { name: '结束会议' })).toHaveAttribute('aria-disabled', 'true')
    expect(screen.getByText('还有 2 个议题未处理')).toBeVisible()
  })

  it('adds an amendment without editing the completed snapshot', async () => {
    apiMock.mockResolvedValueOnce(fixture('completed')).mockResolvedValueOnce({ id: 'am1' }).mockResolvedValueOnce(fixture('completed'))
    render(MeetingWorkspaceView)
    await fireEvent.click(await screen.findByRole('button', { name: '添加更正' }))
    await fireEvent.update(screen.getByLabelText('更正原因'), '补充遗漏信息')
    await fireEvent.update(screen.getByLabelText('更正内容'), '最终负责人为乔安')
    await fireEvent.click(screen.getByRole('button', { name: '保存更正' }))
    await waitFor(() => expect(apiMock).toHaveBeenCalledWith('/api/meetings/m1/amendments', {
      method: 'POST', body: JSON.stringify({ reason: '补充遗漏信息', content_markdown: '最终负责人为乔安', expected_version: 4 }),
    }))
  })
})
