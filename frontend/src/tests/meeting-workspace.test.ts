import { defineComponent, onBeforeUnmount, onMounted } from 'vue'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { apiMock, editorBuffer } = vi.hoisted(() => ({ apiMock: vi.fn(), editorBuffer: { value: '' } }))
vi.mock('../api/client', () => ({ api: apiMock, ApiError: class ApiError extends Error {} }))
vi.mock('vue-router', () => ({ useRoute: () => ({ params: { id: 'm1' } }) }))
vi.mock('../components/MarkdownEditor.vue', () => ({
  default: defineComponent({
    props: ['modelValue', 'label', 'disabled', 'registerEditor'],
    emits: ['update:modelValue'],
    setup(props, { emit, expose }) {
      const writer = (markdown: string) => emit('update:modelValue', markdown)
      expose({
        flush: () => {
          const markdown = editorBuffer.value || props.modelValue
          if (editorBuffer.value) emit('update:modelValue', editorBuffer.value)
          return markdown
        },
      })
      onMounted(() => props.registerEditor?.(writer))
      onBeforeUnmount(() => props.registerEditor?.(null))
      return {}
    },
    template: '<textarea :aria-label="label" :disabled="disabled" :value="modelValue" @input="$emit(\'update:modelValue\', $event.target.value)" />',
  }),
}))

import MeetingWorkspaceView from '../views/MeetingWorkspaceView.vue'
import { registerEditorAssistant } from '../plugins/registry'

const SummaryAssistant = defineComponent({
  emits: ['update:modelValue'],
  template: '<button type="button" @click="$emit(\'update:modelValue\', \'# AI 生成纪要\')">生成会议纪要</button>',
})

const user = { id: 'u1', username: 'lin', display_name: '林宇' }
const meeting = {
  id: 'm1', project: { id: 'p1', name: 'MeetFlow', slug: 'meetflow' }, series: null, title: '迭代评审', purpose_markdown: '', scheduled_start: '2026-07-24T02:00:00Z', scheduled_end: '2026-07-24T03:00:00Z', status: 'ready', host: user, recorder: user, summary_markdown: '', raw_notes_markdown: '', version: 2,
  participants: [{ user, participation_role: 'host', position: 0 }],
  agenda_items: [{ id: 'a1', meeting_id: 'm1', title: '发布方案', agenda_type: 'decision', notes_markdown: '', status: 'planned', position: 0, proposer: null, presenter: null, estimated_minutes: 20, decisions: [], actions: [], open_questions: [], version: 1, created_at: '', updated_at: '' }],
  attachments: [], created_by: user, updated_by: user, created_at: '', updated_at: '',
} as any

function meetingFixture(overrides: Record<string, unknown> = {}) {
  return {
    ...meeting,
    ...overrides,
    agenda_items: overrides.agenda_items ?? meeting.agenda_items.map((item: any) => ({ ...item })),
    attachments: overrides.attachments ?? [],
  }
}

describe('meeting workspace', () => {
  beforeEach(() => { apiMock.mockReset(); apiMock.mockResolvedValue(meeting); editorBuffer.value = '' })

  it('keeps preparation fields on demand instead of above the active agenda', async () => {
    render(MeetingWorkspaceView)
    await screen.findByText('Current topic')
    const preparation = screen.getByRole('button', { name: '准备信息' })
    expect(screen.queryByRole('heading', { name: '会议准备' })).not.toBeInTheDocument()
    await fireEvent.click(preparation)
    expect(screen.getByRole('dialog', { name: '准备信息' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: '会议准备' })).toBeInTheDocument()
  })

  it('keeps a generated meeting summary local until the minutes are explicitly saved', async () => {
    registerEditorAssistant('meeting-summary-editor', SummaryAssistant)
    render(MeetingWorkspaceView)
    await screen.findByText('Current topic')
    const summaryEditor = screen.getByTestId('meeting-summary-editor')
    expect(summaryEditor).toContainElement(screen.getByLabelText('会议纪要'))
    expect(within(summaryEditor).getByText('会议纪要')).toBeVisible()
    await fireEvent.click(within(summaryEditor).getByRole('button', { name: 'AI 工具' }))
    expect(screen.queryByTestId('meeting-inline-summary')).not.toBeInTheDocument()
    expect(screen.queryByTestId('meeting-inline-actions')).not.toBeInTheDocument()

    await fireEvent.click(screen.getByRole('button', { name: '生成会议纪要' }))
    expect(screen.getByLabelText('会议纪要')).toHaveValue('# AI 生成纪要')
    expect(apiMock).not.toHaveBeenCalledWith('/api/meetings/m1', expect.objectContaining({ method: 'PUT' }))

    await fireEvent.click(screen.getByRole('button', { name: '保存会议纪要' }))
    await waitFor(() => expect(apiMock).toHaveBeenCalledWith('/api/meetings/m1', expect.objectContaining({
      method: 'PUT', body: expect.stringContaining('"summary_markdown":"# AI 生成纪要"'),
    })))
    expect(screen.getByRole('status')).toHaveTextContent('纪要已保存')
  })

  it('saves just-entered minutes without waiting for the rich-text debounce', async () => {
    const summary = '确认灰度发布与回滚边界。'
    editorBuffer.value = summary
    render(MeetingWorkspaceView)
    await screen.findByText('Current topic')

    await fireEvent.click(screen.getByRole('button', { name: '保存会议纪要' }))

    await waitFor(() => expect(apiMock).toHaveBeenCalledWith('/api/meetings/m1', expect.objectContaining({
      method: 'PUT', body: expect.stringContaining(`"summary_markdown":"${summary}"`),
    })))
    expect(screen.getByRole('status')).toHaveTextContent('纪要已保存')
  })

  it('exposes the meeting raw notes as an accessible editor', async () => {
    render(MeetingWorkspaceView)
    await screen.findByText('Current topic')

    expect(screen.getByRole('textbox', { name: '整场会议原始笔记' })).toBeInTheDocument()
  })

  it('treats a timezone-less meeting start timestamp as UTC for the live clock', async () => {
    const now = vi.spyOn(Date, 'now').mockReturnValue(Date.UTC(2026, 6, 30, 6, 40, 0))
    apiMock.mockResolvedValue(meetingFixture({ status: 'in_progress', started_at: '2026-07-30T06:38:44.670756' }))

    render(MeetingWorkspaceView)
    await screen.findByText('Current topic')

    expect(screen.getByText('进行 1:15')).toBeVisible()
    now.mockRestore()
  })

  it('saves dirty agenda and meeting drafts before starting with refreshed meeting version', async () => {
    const initial = meetingFixture({ version: 2 })
    const savedAgenda = { ...initial.agenda_items[0], title: '发布方案已确认', version: 2 }
    const refreshed = meetingFixture({ version: 3, agenda_items: [savedAgenda] })
    const savedMeeting = meetingFixture({ version: 4, title: '迭代评审已确认', agenda_items: [savedAgenda] })
    const started = meetingFixture({ version: 5, status: 'in_progress', title: '迭代评审已确认', agenda_items: [savedAgenda] })
    apiMock
      .mockResolvedValueOnce(initial)
      .mockResolvedValueOnce(savedAgenda)
      .mockResolvedValueOnce(refreshed)
      .mockResolvedValueOnce(savedMeeting)
      .mockResolvedValueOnce(started)
    render(MeetingWorkspaceView)
    await screen.findByText('Current topic')

    await fireEvent.update(screen.getByLabelText('议题标题'), '发布方案已确认')
    await fireEvent.click(screen.getByRole('button', { name: '准备信息' }))
    await fireEvent.update(screen.getByLabelText('会议标题'), '迭代评审已确认')
    await fireEvent.click(screen.getByRole('button', { name: '开始会议' }))

    await waitFor(() => expect(apiMock).toHaveBeenCalledTimes(5))
    expect(apiMock.mock.calls.map(([path]) => path)).toEqual([
      '/api/meetings/m1',
      '/api/agenda-items/a1',
      '/api/meetings/m1',
      '/api/meetings/m1',
      '/api/meetings/m1/start',
    ])
    expect(JSON.parse(apiMock.mock.calls[1][1].body)).toMatchObject({ expected_version: 1, title: '发布方案已确认' })
    expect(JSON.parse(apiMock.mock.calls[3][1].body)).toMatchObject({ expected_version: 3, title: '迭代评审已确认' })
    expect(JSON.parse(apiMock.mock.calls[4][1].body)).toEqual({ expected_version: 4 })
  })

  it('does not post a lifecycle action when a dirty agenda draft cannot be saved', async () => {
    apiMock.mockResolvedValueOnce(meetingFixture()).mockRejectedValueOnce(new Error('议题保存失败'))
    render(MeetingWorkspaceView)
    await screen.findByText('Current topic')

    await fireEvent.update(screen.getByLabelText('议题标题'), '无法保存的议题')
    await fireEvent.click(screen.getByRole('button', { name: '开始会议' }))

    await waitFor(() => expect(apiMock).toHaveBeenCalledWith('/api/agenda-items/a1', expect.objectContaining({ method: 'PUT' })))
    expect(apiMock).not.toHaveBeenCalledWith('/api/meetings/m1/start', expect.anything())
    expect(screen.getByLabelText('议题标题')).toHaveValue('无法保存的议题')
  })

  it('does not post a lifecycle action when a dirty meeting draft cannot be saved', async () => {
    apiMock.mockResolvedValueOnce(meetingFixture()).mockRejectedValueOnce(new Error('会议保存失败'))
    render(MeetingWorkspaceView)
    await screen.findByText('Current topic')

    await fireEvent.click(screen.getByRole('button', { name: '准备信息' }))
    await fireEvent.update(screen.getByLabelText('会议标题'), '无法保存的会议')
    await fireEvent.click(screen.getByRole('button', { name: '开始会议' }))

    await waitFor(() => expect(apiMock).toHaveBeenCalledWith('/api/meetings/m1', expect.objectContaining({ method: 'PUT' })))
    expect(apiMock).not.toHaveBeenCalledWith('/api/meetings/m1/start', expect.anything())
    expect(screen.getByLabelText('会议标题')).toHaveValue('无法保存的会议')
  })

  it('posts a clean lifecycle action without refreshing or saving drafts', async () => {
    const started = meetingFixture({ version: 3, status: 'in_progress' })
    apiMock.mockResolvedValueOnce(meetingFixture()).mockResolvedValueOnce(started)
    render(MeetingWorkspaceView)
    await screen.findByText('Current topic')

    await fireEvent.click(screen.getByRole('button', { name: '开始会议' }))

    await waitFor(() => expect(apiMock).toHaveBeenCalledTimes(2))
    expect(apiMock.mock.calls.map(([path]) => path)).toEqual(['/api/meetings/m1', '/api/meetings/m1/start'])
    expect(apiMock.mock.calls[1][1]).toEqual({ method: 'POST', body: JSON.stringify({ expected_version: 2 }) })
  })

  it('starts a draft meeting directly without posting a ready transition', async () => {
    const draftMeeting = meetingFixture({ status: 'draft', version: 2 })
    const started = meetingFixture({ status: 'in_progress', version: 3 })
    apiMock.mockResolvedValueOnce(draftMeeting).mockResolvedValueOnce(started)
    render(MeetingWorkspaceView)
    await screen.findByText('Current topic')

    await fireEvent.click(screen.getByRole('button', { name: '开始会议' }))

    await waitFor(() => expect(apiMock).toHaveBeenCalledTimes(2))
    expect(apiMock.mock.calls.map(([path]) => path)).toEqual([
      '/api/meetings/m1',
      '/api/meetings/m1/start',
    ])
    expect(apiMock).not.toHaveBeenCalledWith('/api/meetings/m1/ready', expect.anything())
  })
})
