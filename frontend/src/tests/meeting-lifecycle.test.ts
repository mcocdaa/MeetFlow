import { fireEvent, render, screen, waitFor, within } from '@testing-library/vue'
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

function completedOutcomeFixture() {
  const meeting = fixture('completed')
  const currentAgenda = meeting.agenda_items[0] as { decisions: unknown[] }
  currentAgenda.decisions = [{ title: '当前可变决策' }]
  if (!meeting.current_snapshot) throw new Error('completed fixture requires a snapshot')
  const snapshot = meeting.current_snapshot as { snapshot_json: Record<string, unknown> }
  snapshot.snapshot_json = {
    meeting: { title: '迭代评审', summary_markdown: '本轮范围已经确认' },
    agenda_items: [
      {
        id: 'a1', title: '发布方案', status: 'completed',
        decisions: [{ id: 'd1', title: '采用灰度发布', decision_markdown: '先向 10% 用户发布。', rationale_markdown: '先验证核心指标。', status: 'final' }],
        actions: [{ id: 'ac1', content: '准备灰度发布清单', priority: 'high', due_date: '2026-07-30', status: 'open' }],
        open_questions: [{ id: 'q1', question_markdown: '回滚阈值是什么？', status: 'open' }],
      },
      { id: 'a2', title: '后续跟进', status: 'completed', decisions: [], actions: [], open_questions: [] },
    ],
    meeting_decisions: [{ id: 'md1', title: '每周复盘一次', decision_markdown: '每周一复盘发布效果。', rationale_markdown: '', status: 'final' }],
    meeting_actions: [],
    meeting_open_questions: [],
  }
  return meeting
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

  it('expands frozen agenda and meeting-level outcomes without reading mutable data', async () => {
    apiMock.mockResolvedValue(completedOutcomeFixture())
    render(MeetingWorkspaceView)

    const first = await screen.findByTestId('completed-agenda-a1')
    const second = screen.getByTestId('completed-agenda-a2')
    expect(first).not.toHaveAttribute('open')
    expect(second).not.toHaveAttribute('open')
    expect(screen.queryByText('当前可变决策')).not.toBeInTheDocument()

    await fireEvent.click(within(first).getByText('发布方案'))
    expect(first).toHaveAttribute('open')
    expect(screen.getByText('采用灰度发布')).toBeVisible()
    expect(screen.getByText('先向 10% 用户发布。')).toBeVisible()
    expect(screen.getByText('准备灰度发布清单')).toBeVisible()
    expect(screen.getByText(/截止：2026-07-30/)).toBeVisible()
    expect(screen.getByText('回滚阈值是什么？')).toBeVisible()

    await fireEvent.click(within(second).getByText('后续跟进'))
    expect(first).toHaveAttribute('open')
    expect(second).toHaveAttribute('open')
    expect(within(second).getByText('本议题未记录产出')).toBeVisible()

    const meetingLevel = screen.getByTestId('completed-meeting-outcomes')
    await fireEvent.click(within(meetingLevel).getByText('会议级产出'))
    expect(meetingLevel).toHaveAttribute('open')
    expect(screen.getByText('每周复盘一次')).toBeVisible()
  })

  it('omits meeting-level outcomes when the completed snapshot has none', async () => {
    apiMock.mockResolvedValue(fixture('completed'))
    render(MeetingWorkspaceView)
    await screen.findByText('议题与产出')
    expect(screen.queryByTestId('completed-meeting-outcomes')).not.toBeInTheDocument()
  })
})
