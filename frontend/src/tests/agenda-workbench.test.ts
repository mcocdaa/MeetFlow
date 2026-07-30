import { defineComponent, ref } from 'vue'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import AgendaDetail from '../components/AgendaDetail.vue'
import AgendaQueue from '../components/AgendaQueue.vue'
import AgendaWorkbench from '../components/AgendaWorkbench.vue'
import type { AgendaItem } from '../domain/meetings'
import { registerEditorAssistant } from '../plugins/registry'

const ActionContextProbe = defineComponent({
  props: ['context'],
  template: '<output data-testid="action-context">{{ JSON.stringify(context.metadata) }}</output>',
})

function outcomeAssistantProbe(testId: string, label: string) {
  return defineComponent({
    props: ['modelValue', 'context', 'disabled'],
    emits: ['notice', 'update:modelValue', 'update:busy'],
    setup() {
      const clicks = ref(0)
      return { clicks, onClick: () => { clicks.value += 1 } }
    },
    template: `<div><button type="button" aria-label="${label}" @click="onClick">${label}</button><output data-testid="${testId}">{{ clicks }}</output></div>`,
  })
}

const { apiMock, editorBuffer } = vi.hoisted(() => ({ apiMock: vi.fn(), editorBuffer: { value: '' } }))
vi.mock('../api/client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api/client')>()
  return { ...actual, api: apiMock }
})
vi.mock('../components/MarkdownEditor.vue', () => ({
  default: defineComponent({
    props: ['modelValue', 'label'],
    emits: ['update:modelValue'],
    setup(props, { emit, expose }) {
      expose({
        flush: () => {
          const markdown = editorBuffer.value || props.modelValue
          if (editorBuffer.value) emit('update:modelValue', editorBuffer.value)
          return markdown
        },
      })
      return {}
    },
    template: '<textarea :aria-label="label" :value="modelValue" @input="$emit(\'update:modelValue\', $event.target.value)" />',
  }),
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

function emptyMeetingFixture() {
  return { ...meetingFixture(), agenda_items: [] }
}

type AgendaWorkbenchHandle = { flushCurrentDraft: () => Promise<boolean> }

const AgendaFlushHarness = defineComponent({
  components: { AgendaWorkbench },
  setup() {
    const workbench = ref<AgendaWorkbenchHandle | null>(null)
    const result = ref('')
    const reloads = ref(0)

    async function flush() {
      result.value = String(await workbench.value!.flushCurrentDraft())
    }

    return { flush, meeting: meetingFixture(), reloads, result, workbench }
  },
  template: '<AgendaWorkbench ref="workbench" :meeting="meeting" @reload="reloads += 1" /><button type="button" @click="flush">刷新当前议题草稿</button><output data-testid="flush-result">{{ result }}</output><output data-testid="reload-count">{{ reloads }}</output>',
})

describe('agenda workbench', () => {
  beforeEach(() => {
    apiMock.mockReset()
    apiMock.mockResolvedValue({})
    editorBuffer.value = ''
  })

  it('keeps the active topic and selectable queue in one shared workbench surface', async () => {
    apiMock.mockResolvedValueOnce({ ...meetingFixture().agenda_items[1], status: 'in_progress', version: 2 })
    render(AgendaWorkbench, { props: { meeting: meetingFixture() } })
    const workbench = screen.getByTestId('meeting-workbench')
    const detail = screen.getByTestId('agenda-detail')
    const queue = screen.getByTestId('agenda-queue')

    expect(workbench).toHaveClass('workspace-section')
    expect(workbench).toContainElement(detail)
    expect(workbench).toContainElement(queue)
    expect(detail.compareDocumentPosition(queue) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    expect(detail).not.toHaveClass('workspace-section')
    expect(queue).not.toHaveClass('workspace-section')
    expect(screen.getByLabelText('议题标题')).toHaveValue('进展同步')
    expect(screen.getByTestId('agenda-row-a1')).toHaveClass('selected', 'agenda-status-in_progress')

    await fireEvent.click(screen.getByTestId('agenda-row-a2').querySelector('button')!)
    await waitFor(() => expect(apiMock).toHaveBeenCalledWith('/api/agenda-items/a2/start', {
      method: 'POST', body: JSON.stringify({ expected_version: 1 }),
    }))
    expect(screen.getByLabelText('议题标题')).toHaveValue('发布方案')
  })

  it('keeps the empty topic affordance and queue inside the shared surface', () => {
    render(AgendaWorkbench, { props: { meeting: emptyMeetingFixture() } })
    const workbench = screen.getByTestId('meeting-workbench')
    const detail = screen.getByTestId('agenda-detail')
    const queue = screen.getByTestId('agenda-queue')

    expect(workbench).toContainElement(detail)
    expect(workbench).toContainElement(queue)
    expect(detail).toHaveClass('agenda-empty-compact')
    expect(within(detail).getByText('Current topic')).toBeVisible()
    expect(detail.compareDocumentPosition(queue) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    expect(within(queue).getByRole('button', { name: '+ 议题' })).toBeVisible()
    expect(within(detail).queryByRole('button', { name: '添加议题' })).not.toBeInTheDocument()
  })

  it('uses a five minute estimate for a newly queued topic', async () => {
    const added = { ...meetingFixture().agenda_items[0], id: 'a3', title: '新的议题', estimated_minutes: 5 }
    apiMock.mockResolvedValueOnce(added)
    render(AgendaQueue, { props: { meeting: meetingFixture() } })

    await fireEvent.click(screen.getByRole('button', { name: '+ 议题' }))
    expect(screen.getByLabelText('预计时长（分钟）')).toHaveValue(5)
    await fireEvent.update(screen.getByLabelText('议题标题'), '新的议题')
    await fireEvent.click(screen.getByRole('button', { name: '插入队尾' }))

    await waitFor(() => expect(apiMock).toHaveBeenCalledWith('/api/meetings/m1/agenda-items?expected_meeting_version=4', {
      method: 'POST',
      body: JSON.stringify({ title: '新的议题', agenda_type: 'discussion', notes_markdown: '', position: 2, estimated_minutes: 5 }),
    }))
  })

  it('does not expose agenda record versions or a separate skip action', () => {
    render(AgendaDetail, { props: { meeting: meetingFixture(), item: meetingFixture().agenda_items[0] } })
    expect(screen.queryByText(/版本\s*2/)).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /跳过/ })).not.toBeInTheDocument()
  })

  it('does not render a separate start-topic action', () => {
    const planned = meetingFixture().agenda_items[1]
    render(AgendaDetail, { props: { meeting: meetingFixture(), item: planned } })

    expect(screen.queryByRole('button', { name: '开始此议题' })).not.toBeInTheDocument()
  })

  it('preserves a completed topic as a non-current queue state', () => {
    const meeting = meetingFixture()
    const completed = { ...meeting.agenda_items[0], status: 'completed' } as AgendaItem
    render(AgendaQueue, { props: { meeting: { ...meeting, agenda_items: [completed, ...meeting.agenda_items.slice(1)] }, selectedId: meeting.agenda_items[1].id } })

    expect(screen.getByTestId('agenda-row-a1')).toHaveClass('agenda-status-completed')
    expect(screen.getByTestId('agenda-row-a1')).not.toHaveClass('selected')
  })

  it('exposes a clean current draft flush that does not request or reload', async () => {
    render(AgendaFlushHarness)
    await fireEvent.click(screen.getByRole('button', { name: '刷新当前议题草稿' }))

    await waitFor(() => expect(screen.getByTestId('flush-result')).toHaveTextContent('false'))
    expect(apiMock).not.toHaveBeenCalled()
    expect(screen.getByTestId('reload-count')).toHaveTextContent('0')
  })

  it('flushes a dirty current draft once without emitting a workbench reload', async () => {
    const saved = { ...meetingFixture().agenda_items[0], title: '已确认进展', version: 3 }
    apiMock.mockResolvedValueOnce(saved)
    render(AgendaFlushHarness)

    await fireEvent.update(screen.getByLabelText('议题标题'), '已确认进展')
    await fireEvent.click(screen.getByRole('button', { name: '刷新当前议题草稿' }))

    await waitFor(() => expect(screen.getByTestId('flush-result')).toHaveTextContent('true'))
    expect(apiMock).toHaveBeenCalledWith('/api/agenda-items/a1', {
      method: 'PUT',
      body: JSON.stringify({ expected_version: 2, title: '已确认进展', agenda_type: 'information', notes_markdown: '', estimated_minutes: 20 }),
    })
    expect(screen.getByTestId('reload-count')).toHaveTextContent('0')

    await fireEvent.click(screen.getByRole('button', { name: '刷新当前议题草稿' }))
    expect(apiMock).toHaveBeenCalledTimes(1)
  })

  it('only manually saves a dirty topic and emits changed after success', async () => {
    const changed = vi.fn()
    apiMock.mockResolvedValueOnce({ ...meetingFixture().agenda_items[0], title: '更新后的进展', version: 3 })
    render(AgendaDetail, { props: { meeting: meetingFixture(), item: meetingFixture().agenda_items[0] }, attrs: { onChanged: changed } })

    await fireEvent.click(screen.getByRole('button', { name: '保存议题' }))
    expect(apiMock).not.toHaveBeenCalled()

    await fireEvent.update(screen.getByLabelText('议题标题'), '更新后的进展')
    await fireEvent.click(screen.getByRole('button', { name: '保存议题' }))
    await waitFor(() => expect(changed).toHaveBeenCalledTimes(1))
    expect(apiMock).toHaveBeenCalledTimes(1)
  })

  it('saves a just-entered agenda record without waiting for the rich-text debounce', async () => {
    const item = meetingFixture().agenda_items[0]
    const notes = '@决策: 采用灰度发布'
    editorBuffer.value = notes
    apiMock.mockResolvedValueOnce({ ...item, notes_markdown: notes, version: 3 })
    render(AgendaDetail, { props: { meeting: meetingFixture(), item } })

    await fireEvent.click(screen.getByRole('button', { name: '保存议题' }))

    await waitFor(() => expect(apiMock).toHaveBeenCalledWith('/api/agenda-items/a1', {
      method: 'PUT',
      body: JSON.stringify({ expected_version: 2, title: '进展同步', agenda_type: 'information', notes_markdown: notes, estimated_minutes: 20 }),
    }))
  })

  it('uses the accepted version when agenda completion follows a manual save', async () => {
    const item = meetingFixture().agenda_items[0]
    const changed = vi.fn()
    const advanced = vi.fn()
    apiMock
      .mockResolvedValueOnce({ ...item, title: '进展已确认', version: 3 })
      .mockResolvedValueOnce({ agenda_item: { ...item, title: '进展已确认', version: 4 }, next_agenda_item_id: 'a2' })
    render(AgendaDetail, { props: { meeting: meetingFixture(), item }, attrs: { onChanged: changed, onAdvance: advanced } })

    await fireEvent.update(screen.getByLabelText('议题标题'), '进展已确认')
    await fireEvent.click(screen.getByRole('button', { name: '保存议题' }))
    await waitFor(() => expect(changed).toHaveBeenCalledTimes(1))
    await fireEvent.click(screen.getByRole('button', { name: '完成议题并进入下一项' }))

    await waitFor(() => expect(apiMock).toHaveBeenCalledWith('/api/agenda-items/a1/complete-and-advance', {
      method: 'POST', body: JSON.stringify({ expected_version: 3 }),
    }))
    expect(advanced).toHaveBeenCalledWith('a2')
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
    expect(screen.getByTestId('flow-actions')).toHaveTextContent('完成议题并进入下一项')
    expect(screen.getByTestId('outcome-actions')).not.toContainElement(screen.getByRole('button', { name: '完成议题并进入下一项' }))
  })

  it('places outcome assistants in every editor without treating editor clicks as assistant clicks', async () => {
    registerEditorAssistant('decision-composer', outcomeAssistantProbe('decision-assistant-clicks', 'AI 建议决策'))
    registerEditorAssistant('action-composer', outcomeAssistantProbe('action-assistant-clicks', 'AI 建议行动项'))
    registerEditorAssistant('question-composer', outcomeAssistantProbe('question-assistant-clicks', 'AI 梳理开放问题'))
    render(AgendaDetail, { props: { meeting: meetingFixture(), item: meetingFixture().agenda_items[0] } })

    await fireEvent.click(screen.getByRole('button', { name: '+ 决策' }))
    expect(screen.getByTestId('decision-composer')).toContainElement(screen.getByLabelText('决策内容'))
    await fireEvent.click(screen.getByLabelText('决策内容'))
    expect(screen.queryByTestId('decision-assistant-clicks')).not.toBeInTheDocument()
    await fireEvent.click(within(screen.getByTestId('decision-composer')).getByRole('button', { name: 'AI 工具' }))
    expect(screen.getByTestId('decision-assistant-clicks')).toHaveTextContent('0')
    await fireEvent.click(screen.getByRole('button', { name: 'AI 建议决策' }))
    expect(screen.getByTestId('decision-assistant-clicks')).toHaveTextContent('1')
    await fireEvent.click(screen.getByRole('button', { name: '关闭' }))

    registerEditorAssistant('action-composer', ActionContextProbe)
    await fireEvent.click(screen.getByRole('button', { name: '+ 行动' }))
    expect(screen.getByTestId('action-composer')).toContainElement(screen.getByLabelText('行动项内容'))
    await fireEvent.click(screen.getByLabelText('行动项内容'))
    expect(screen.queryByTestId('action-assistant-clicks')).not.toBeInTheDocument()
    await fireEvent.click(within(screen.getByTestId('action-composer')).getByRole('button', { name: 'AI 工具' }))
    expect(screen.getByTestId('action-assistant-clicks')).toHaveTextContent('0')
    await fireEvent.click(screen.getByRole('button', { name: 'AI 建议行动项' }))
    expect(screen.getByTestId('action-assistant-clicks')).toHaveTextContent('1')
    expect(JSON.parse(screen.getByTestId('action-context').textContent ?? '{}')).toMatchObject({
      projectId: 'p1', meetingId: 'm1', agendaId: 'a1', participants: [users.lin, users.qiao],
    })
    await fireEvent.click(screen.getByRole('button', { name: '关闭' }))

    await fireEvent.click(screen.getByRole('button', { name: '+ 开放问题' }))
    expect(screen.getByTestId('question-composer')).toContainElement(screen.getByLabelText('开放问题内容'))
    await fireEvent.click(screen.getByLabelText('开放问题内容'))
    expect(screen.queryByTestId('question-assistant-clicks')).not.toBeInTheDocument()
    await fireEvent.click(within(screen.getByTestId('question-composer')).getByRole('button', { name: 'AI 工具' }))
    expect(screen.getByTestId('question-assistant-clicks')).toHaveTextContent('0')
    await fireEvent.click(screen.getByRole('button', { name: 'AI 梳理开放问题' }))
    expect(screen.getByTestId('question-assistant-clicks')).toHaveTextContent('1')
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
