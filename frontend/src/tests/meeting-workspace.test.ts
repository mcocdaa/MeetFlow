import { defineComponent, onBeforeUnmount, onMounted } from 'vue'
import { fireEvent, screen, waitFor, within } from '@testing-library/vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { apiMock, apiDownloadMock, editorBuffer, routeState } = vi.hoisted(() => ({
  apiMock: vi.fn(),
  apiDownloadMock: vi.fn(),
  editorBuffer: { value: '' },
  routeState: { query: {} as Record<string, string> },
}))
vi.mock('../api/client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api/client')>()
  return { ...actual, api: apiMock, apiDownload: apiDownloadMock }
})
vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { id: 'm1' }, query: routeState.query }),
  onBeforeRouteLeave: () => undefined,
}))
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
import { renderWithProviders } from './helpers'

const SummaryAssistant = defineComponent({
  emits: ['update:modelValue'],
  template: '<button type="button" @click="$emit(\'update:modelValue\', \'# AI 生成纪要\')">生成会议纪要</button>',
})

const user = { id: 'u1', username: 'lin', display_name: '林宇' }
const qiao = { id: 'u2', username: 'qiao', display_name: '乔安' }

function projectFixture() {
  return {
    id: 'p1', name: 'MeetFlow', slug: 'meetflow', version: 1,
    memberships: [
      { role: 'member', user },
      { role: 'member', user: qiao },
    ],
  }
}

function commentFixture(id: string, body: string) {
  return {
    id, parent_id: null, body_markdown: body, version: 1, creator: user, mentions: [], edited_at: null,
    created_at: '2026-07-24T02:00:00Z', replies: [], reply_next_cursor: null, resolved_at: null,
    resolved_by: null, can_edit: false, can_delete: false, can_resolve: false,
  }
}

function commentDeepLinkApi(items: ReturnType<typeof commentFixture>[]) {
  return (path: string) => {
    if (path.startsWith('/api/comments?')) return Promise.resolve({ items, next_cursor: null })
    if (path.startsWith('/api/projects/')) return Promise.resolve(projectFixture())
    return Promise.resolve(meetingFixture())
  }
}

const meeting = {
  id: 'm1', project: { id: 'p1', name: 'MeetFlow', slug: 'meetflow' }, series: null, title: '迭代评审', purpose_markdown: '', scheduled_start: '2026-07-24T02:00:00Z', scheduled_end: '2026-07-24T03:00:00Z', status: 'ready', host: user, recorder: user, summary_markdown: '', raw_notes_markdown: '', version: 2,
  capabilities: { can_manage: true, can_contribute: true, can_comment: true },
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
  beforeEach(() => {
    apiMock.mockReset()
    apiDownloadMock.mockReset()
    apiMock.mockResolvedValue(meeting)
    editorBuffer.value = ''
    routeState.query = {}
  })

  it('safely falls back to read-only when an older response lacks capabilities', async () => {
    apiMock.mockResolvedValue(meetingFixture({ capabilities: undefined }))
    renderWithProviders(MeetingWorkspaceView)

    expect(await screen.findByRole('heading', { name: '迭代评审' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '开始会议' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '取消会议' })).not.toBeInTheDocument()
  })

  it('keeps preparation fields on demand instead of above the active agenda', async () => {
    renderWithProviders(MeetingWorkspaceView)
    await screen.findByText('Current topic')
    const preparation = screen.getByRole('button', { name: '准备信息' })
    expect(screen.queryByText('会议准备')).not.toBeInTheDocument()
    await fireEvent.click(preparation)
    expect(await screen.findByText('会议准备')).toBeVisible()
    expect(screen.getByLabelText('会议标题')).toHaveValue('迭代评审')
    expect((screen.getByLabelText('开始时间') as HTMLInputElement).value).toMatch(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/)
    expect((screen.getByLabelText('结束时间') as HTMLInputElement).value).toMatch(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/)
    expect(screen.getByLabelText('会议目的')).toBeVisible()
    expect(screen.getByLabelText('主持')).toBeVisible()
    expect(screen.getByLabelText('记录')).toBeVisible()
    expect(screen.getByRole('button', { name: '添加参与人' })).toBeVisible()
  })

  it('saves the preparation form with the full participant list', async () => {
    const initial = meetingFixture({
      version: 4,
      participants: [
        { user, participation_role: 'host', position: 0 },
        { user: qiao, participation_role: 'attendee', position: 1 },
      ],
    })
    const saved = meetingFixture({ version: 5 })
    apiMock
      .mockResolvedValueOnce(initial)
      .mockResolvedValueOnce(projectFixture())
      .mockResolvedValueOnce(saved)
    renderWithProviders(MeetingWorkspaceView)
    await screen.findByText('Current topic')

    await fireEvent.click(screen.getByRole('button', { name: '准备信息' }))
    await screen.findByText('会议准备')

    const rows = document.querySelectorAll('.participant-editor-row')
    expect(rows).toHaveLength(2)
    await fireEvent.click(rows[1].querySelector('.participant-role-select .n-base-selection')!)
    const presenterOption = await waitFor(() => {
      const option = [...document.querySelectorAll('.n-base-select-option__content')]
        .find((candidate) => candidate.textContent === '主讲')
      if (!option) throw new Error('role option is not open yet')
      return option
    })
    await fireEvent.click(presenterOption)

    await fireEvent.click(screen.getAllByRole('button', { name: '移除参与人' })[0])
    expect(document.querySelectorAll('.participant-editor-row')).toHaveLength(1)

    await fireEvent.click(screen.getByRole('button', { name: '保存准备信息' }))

    await waitFor(() => expect(apiMock).toHaveBeenCalledWith('/api/meetings/m1', expect.objectContaining({ method: 'PUT' })))
    const putCall = apiMock.mock.calls.find(([path, init]) => (
      path === '/api/meetings/m1' && (init as RequestInit | undefined)?.method === 'PUT'
    ))
    const payload = JSON.parse((putCall?.[1] as RequestInit).body as string)
    expect(payload).toMatchObject({
      expected_version: 4,
      title: '迭代评审',
      participants: [{ user_id: 'u2', participation_role: 'presenter' }],
    })
  })

  it('falls back to the current participants when the project members cannot be read', async () => {
    apiMock
      .mockResolvedValueOnce(meetingFixture())
      .mockRejectedValueOnce(new Error('项目读取失败'))
    renderWithProviders(MeetingWorkspaceView)
    await screen.findByText('Current topic')

    await fireEvent.click(screen.getByRole('button', { name: '准备信息' }))

    expect(await screen.findByText('成员列表不可用，仅显示当前参与人')).toBeVisible()
    expect(document.querySelectorAll('.participant-editor-row')).toHaveLength(1)
  })

  it('surfaces a locked meeting message instead of the inline preparation alert', async () => {
    const { ApiError } = await import('../api/client')
    apiMock
      .mockResolvedValueOnce(meetingFixture())
      .mockResolvedValueOnce(projectFixture())
      .mockRejectedValueOnce(new ApiError(409, 'meeting_locked', '已结束的会议不可直接修改'))
    renderWithProviders(MeetingWorkspaceView)
    await screen.findByText('Current topic')

    await fireEvent.click(screen.getByRole('button', { name: '准备信息' }))
    await screen.findByText('会议准备')
    await fireEvent.click(screen.getByRole('button', { name: '保存准备信息' }))

    expect(await screen.findByText('已结束的会议不可直接修改')).toBeVisible()
  })

  it('keeps a generated meeting summary local until the minutes are explicitly saved', async () => {
    registerEditorAssistant('meeting-summary-editor', SummaryAssistant)
    renderWithProviders(MeetingWorkspaceView)
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
    renderWithProviders(MeetingWorkspaceView)
    await screen.findByText('Current topic')

    await fireEvent.click(screen.getByRole('button', { name: '保存会议纪要' }))

    await waitFor(() => expect(apiMock).toHaveBeenCalledWith('/api/meetings/m1', expect.objectContaining({
      method: 'PUT', body: expect.stringContaining(`"summary_markdown":"${summary}"`),
    })))
    expect(screen.getByRole('status')).toHaveTextContent('纪要已保存')
  })

  it('exposes the meeting raw notes as an accessible editor', async () => {
    renderWithProviders(MeetingWorkspaceView)
    await screen.findByText('Current topic')

    expect(screen.getByRole('textbox', { name: '整场会议原始笔记' })).toBeInTheDocument()
  })

  it('treats a timezone-less meeting start timestamp as UTC for the live clock', async () => {
    const now = vi.spyOn(Date, 'now').mockReturnValue(Date.UTC(2026, 6, 30, 6, 40, 0))
    apiMock.mockResolvedValue(meetingFixture({ status: 'in_progress', started_at: '2026-07-30T06:38:44.670756' }))

    renderWithProviders(MeetingWorkspaceView)
    await screen.findByText('Current topic')

    expect(screen.getByText('进行 1:15')).toBeVisible()
    now.mockRestore()
  })

  it('saves dirty agenda and meeting drafts before starting with refreshed meeting version', async () => {
    const initial = meetingFixture({ version: 2 })
    const savedAgenda = { ...initial.agenda_items[0], title: '发布方案已确认', version: 2 }
    const refreshed = meetingFixture({ version: 3, agenda_items: [savedAgenda] })
    const savedMeeting = meetingFixture({ version: 4, summary_markdown: '迭代评审已确认', agenda_items: [savedAgenda] })
    const started = meetingFixture({ version: 5, status: 'in_progress', summary_markdown: '迭代评审已确认', agenda_items: [savedAgenda] })
    apiMock
      .mockResolvedValueOnce(initial)
      .mockResolvedValueOnce(projectFixture())
      .mockResolvedValueOnce(savedAgenda)
      .mockResolvedValueOnce(refreshed)
      .mockResolvedValueOnce(savedMeeting)
      .mockResolvedValueOnce(started)
    renderWithProviders(MeetingWorkspaceView)
    await screen.findByText('Current topic')

    await fireEvent.update(screen.getByLabelText('议题标题'), '发布方案已确认')
    await fireEvent.update(screen.getByLabelText('会议纪要'), '迭代评审已确认')
    await fireEvent.click(screen.getByRole('button', { name: '开始会议' }))

    await waitFor(() => expect(apiMock).toHaveBeenCalledTimes(6))
    expect(apiMock.mock.calls.map(([path]) => path)).toEqual([
      '/api/meetings/m1',
      '/api/projects/p1',
      '/api/agenda-items/a1',
      '/api/meetings/m1',
      '/api/meetings/m1',
      '/api/meetings/m1/start',
    ])
    expect(JSON.parse(apiMock.mock.calls[2][1].body)).toMatchObject({ expected_version: 1, title: '发布方案已确认' })
    expect(JSON.parse(apiMock.mock.calls[4][1].body)).toMatchObject({ expected_version: 3, summary_markdown: '迭代评审已确认' })
    expect(JSON.parse(apiMock.mock.calls[5][1].body)).toEqual({ expected_version: 4 })
  })

  it('does not post a lifecycle action when a dirty agenda draft cannot be saved', async () => {
    apiMock
      .mockResolvedValueOnce(meetingFixture())
      .mockResolvedValueOnce(projectFixture())
      .mockRejectedValueOnce(new Error('议题保存失败'))
    renderWithProviders(MeetingWorkspaceView)
    await screen.findByText('Current topic')

    await fireEvent.update(screen.getByLabelText('议题标题'), '无法保存的议题')
    await fireEvent.click(screen.getByRole('button', { name: '开始会议' }))

    await waitFor(() => expect(apiMock).toHaveBeenCalledWith('/api/agenda-items/a1', expect.objectContaining({ method: 'PUT' })))
    expect(apiMock).not.toHaveBeenCalledWith('/api/meetings/m1/start', expect.anything())
    expect(screen.getByLabelText('议题标题')).toHaveValue('无法保存的议题')
  })

  it('does not post a lifecycle action when a dirty meeting draft cannot be saved', async () => {
    apiMock
      .mockResolvedValueOnce(meetingFixture())
      .mockResolvedValueOnce(projectFixture())
      .mockRejectedValueOnce(new Error('会议保存失败'))
    renderWithProviders(MeetingWorkspaceView)
    await screen.findByText('Current topic')

    await fireEvent.update(screen.getByLabelText('会议纪要'), '无法保存的会议')
    await fireEvent.click(screen.getByRole('button', { name: '开始会议' }))

    await waitFor(() => expect(apiMock).toHaveBeenCalledWith('/api/meetings/m1', expect.objectContaining({ method: 'PUT' })))
    expect(apiMock).not.toHaveBeenCalledWith('/api/meetings/m1/start', expect.anything())
    expect(screen.getByLabelText('会议纪要')).toHaveValue('无法保存的会议')
  })

  it('posts a clean lifecycle action without refreshing or saving drafts', async () => {
    const started = meetingFixture({ version: 3, status: 'in_progress' })
    apiMock
      .mockResolvedValueOnce(meetingFixture())
      .mockResolvedValueOnce(projectFixture())
      .mockResolvedValueOnce(started)
    renderWithProviders(MeetingWorkspaceView)
    await screen.findByText('Current topic')

    await fireEvent.click(screen.getByRole('button', { name: '开始会议' }))

    await waitFor(() => expect(apiMock).toHaveBeenCalledTimes(3))
    expect(apiMock.mock.calls.map(([path]) => path)).toEqual(['/api/meetings/m1', '/api/projects/p1', '/api/meetings/m1/start'])
    expect(apiMock.mock.calls[2][1]).toEqual({ method: 'POST', body: JSON.stringify({ expected_version: 2 }) })
  })

  it('starts a draft meeting directly without posting a ready transition', async () => {
    const draftMeeting = meetingFixture({ status: 'draft', version: 2 })
    const started = meetingFixture({ status: 'in_progress', version: 3 })
    apiMock
      .mockResolvedValueOnce(draftMeeting)
      .mockResolvedValueOnce(projectFixture())
      .mockResolvedValueOnce(started)
    renderWithProviders(MeetingWorkspaceView)
    await screen.findByText('Current topic')

    await fireEvent.click(screen.getByRole('button', { name: '开始会议' }))

    await waitFor(() => expect(apiMock).toHaveBeenCalledTimes(3))
    expect(apiMock.mock.calls.map(([path]) => path)).toEqual([
      '/api/meetings/m1',
      '/api/projects/p1',
      '/api/meetings/m1/start',
    ])
    expect(apiMock).not.toHaveBeenCalledWith('/api/meetings/m1/ready', expect.anything())
  })

  it('offers bounded exports after a meeting is completed', async () => {
    apiMock
      .mockResolvedValueOnce(meetingFixture({ status: 'completed' }))
      .mockResolvedValueOnce(projectFixture())
    apiDownloadMock.mockResolvedValue({ blob: new Blob(['# meeting']), filename: 'meeting.md' })
    Object.defineProperty(URL, 'createObjectURL', { configurable: true, value: vi.fn(() => 'blob:meeting') })
    Object.defineProperty(URL, 'revokeObjectURL', { configurable: true, value: vi.fn() })
    const anchorClick = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined)
    renderWithProviders(MeetingWorkspaceView)
    await screen.findByText('迭代评审')

    await fireEvent.click(screen.getByRole('button', { name: '导出 Markdown' }))

    await waitFor(() => expect(apiDownloadMock).toHaveBeenCalledWith('/api/meetings/m1/plugin-exports/meeting-export.markdown', { method: 'POST' }))
    anchorClick.mockRestore()
  })

  it('protects dirty meeting drafts from browser unload', async () => {
    renderWithProviders(MeetingWorkspaceView)
    await screen.findByText('Current topic')
    await fireEvent.update(screen.getByLabelText('会议纪要'), '未保存纪要')

    const event = new Event('beforeunload', { cancelable: true })
    window.dispatchEvent(event)
    expect(event.defaultPrevented).toBe(true)
  })

  it('opens the comments drawer from the ?comment deep link and renders the target comment', async () => {
    routeState.query = { comment: 'c9' }
    apiMock.mockImplementation(commentDeepLinkApi([commentFixture('c9', '深链评论')]))
    renderWithProviders(MeetingWorkspaceView)

    expect(await screen.findByText('深链评论')).toBeVisible()
    expect(document.querySelector('[data-comment-id="c9"]')).not.toBeNull()
  })

  it('shows the earlier-discussion hint when the deep-linked comment is not loaded', async () => {
    routeState.query = { comment: 'c9' }
    apiMock.mockImplementation(commentDeepLinkApi([commentFixture('c1', '另一条评论')]))
    renderWithProviders(MeetingWorkspaceView)

    expect(await screen.findByTestId('comment-focus-missing')).toBeVisible()
    expect(document.querySelector('[data-comment-id="c9"]')).toBeNull()
  })
})
