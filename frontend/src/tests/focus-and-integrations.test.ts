import { defineComponent } from 'vue'
import { fireEvent, screen, waitFor } from '@testing-library/vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { apiMock, editorBuffer } = vi.hoisted(() => ({
  apiMock: vi.fn(),
  editorBuffer: { value: '' },
}))

vi.mock('../api/client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api/client')>()
  return { ...actual, api: apiMock }
})

vi.mock('../components/MarkdownEditor.vue', () => ({
  default: defineComponent({
    props: ['modelValue', 'label', 'disabled', 'registerEditor'],
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
    template: '<textarea :aria-label="label" :disabled="disabled" :value="modelValue" @input="$emit(\'update:modelValue\', $event.target.value)" />',
  }),
}))

import AgendaDetail from '../components/AgendaDetail.vue'
import CalendarSubscriptionModal from '../components/CalendarSubscriptionModal.vue'
import type { Meeting } from '../domain/meetings'
import FocusMode from '../components/FocusMode.vue'
import WebhookNotifyModal from '../components/WebhookNotifyModal.vue'
import { renderWithProviders } from './helpers'

const testUser = { id: 'u1', username: 'lin', display_name: '林宇' }

function meetingFixture(): Meeting {
  const common = {
    meeting_id: 'm1',
    notes_markdown: '讨论内容包含 @行动:[open][@lin][2026-10-01] 推进架构重构',
    proposer: null,
    presenter: testUser,
    estimated_minutes: 20,
    decisions: [
      { id: 'd1', title: '采用轻量单容器方案', is_derived: true, version: 1 },
    ],
    actions: [
      {
        id: 'act1',
        content: '推进架构重构',
        status: 'open' as const,
        priority: 'high' as const,
        due_date: '2026-10-01',
        owner: testUser,
        is_derived: true,
        version: 1,
      },
    ],
    open_questions: [
      { id: 'q1', question_markdown: '是否集成钉钉群卡片？', is_derived: false, version: 1 },
    ],
    created_at: '',
    updated_at: '',
  }

  return {
    id: 'm1',
    project: { id: 'p1', name: 'MeetFlow', slug: 'meetflow' },
    series: null,
    title: '架构演进评审',
    purpose_markdown: '',
    scheduled_start: '2026-07-24T02:00:00Z',
    scheduled_end: '2026-07-24T03:00:00Z',
    started_at: '2026-07-24T02:05:00Z',
    status: 'in_progress' as const,
    host: testUser,
    recorder: testUser,
    summary_markdown: '',
    raw_notes_markdown: '',
    version: 3,
    capabilities: { can_manage: true, can_contribute: true, can_comment: true },
    participants: [{ user: testUser, participation_role: 'host' as const, position: 0 }],
    agenda_items: [
      { ...common, id: 'a1', title: '核心状态机设计', agenda_type: 'decision' as const, status: 'in_progress' as const, position: 0, version: 1 },
    ],
    created_by: testUser,
    updated_by: testUser,
    created_at: '',
    updated_at: '',
  } as unknown as Meeting
}

describe('P0 Features: Bidirectional Actions, Focus Mode, Calendar & Webhooks', () => {
  beforeEach(() => {
    apiMock.mockReset()
    editorBuffer.value = ''
  })

  it('toggles action status via one-click checkbox and updates backend', async () => {
    const meeting = meetingFixture()
    apiMock.mockImplementation((url: string, init?: RequestInit) => {
      if (url.includes('/api/actions/act1') && init?.method === 'PUT') {
        const body = JSON.parse(init.body as string)
        return Promise.resolve({
          ...meeting.agenda_items[0].actions[0],
          status: body.status,
          version: 2,
        })
      }
      return Promise.resolve(meeting)
    })

    const onChanged = vi.fn()
    renderWithProviders(AgendaDetail, {
      props: {
        meeting,
        item: meeting.agenda_items[0] as any,
        canContribute: true,
        onChanged,
      },
    })

    expect(screen.getByText('推进架构重构')).toBeInTheDocument()
    const checkbox = screen.getByTitle('切换完成状态')
    expect(checkbox).toBeInTheDocument()

    // Click to toggle to done
    await fireEvent.click(checkbox)

    expect(apiMock).toHaveBeenCalledWith('/api/actions/act1', expect.objectContaining({
      method: 'PUT',
      body: JSON.stringify({ status: 'done', expected_version: 1 }),
    }))
    expect(onChanged).toHaveBeenCalled()
  })

  it('cycles action status via status pill button', async () => {
    const meeting = meetingFixture()
    apiMock.mockImplementation((url: string, init?: RequestInit) => {
      if (url.includes('/api/actions/act1') && init?.method === 'PUT') {
        const body = JSON.parse(init.body as string)
        return Promise.resolve({
          ...meeting.agenda_items[0].actions[0],
          status: body.status,
          version: 2,
        })
      }
      return Promise.resolve(meeting)
    })

    renderWithProviders(AgendaDetail, {
      props: {
        meeting,
        item: meeting.agenda_items[0] as any,
        canContribute: true,
      },
    })

    const statusPill = screen.getByTitle('点击切换状态')
    expect(statusPill).toHaveTextContent('待办')

    // Click cycles open -> in_progress
    await fireEvent.click(statusPill)

    expect(apiMock).toHaveBeenCalledWith('/api/actions/act1', expect.objectContaining({
      method: 'PUT',
      body: JSON.stringify({ status: 'in_progress', expected_version: 1 }),
    }))
  })

  it('renders Focus Mode with floating bar, progress, and split panes', async () => {
    const meeting = meetingFixture()
    apiMock.mockImplementation((url: string) => {
      if (url.includes('/complete-and-advance')) {
        return Promise.resolve({ next_agenda_item_id: null })
      }
      return Promise.resolve(meeting)
    })

    const onReload = vi.fn()
    const onUpdateShow = vi.fn()
    renderWithProviders(FocusMode, {
      props: {
        show: true,
        meeting: meeting as any,
        canContribute: true,
        onReload,
        'onUpdate:show': onUpdateShow,
      },
    })

    expect(screen.getByTestId('focus-mode-view')).toBeInTheDocument()
    expect(screen.getAllByText('核心状态机设计').length).toBeGreaterThan(0)
    expect(screen.getByText('主讲: 林宇')).toBeInTheDocument()
    expect(screen.getByText('实时决议与待办')).toBeInTheDocument()
    expect(screen.getByText('采用轻量单容器方案')).toBeInTheDocument()

    // Test advance button
    const advanceBtn = screen.getByRole('button', { name: /完成并下一项/ })
    await fireEvent.click(advanceBtn)

    expect(apiMock).toHaveBeenCalledWith(
      '/api/agenda-items/a1/complete-and-advance',
      expect.objectContaining({ method: 'POST' }),
    )
    expect(onReload).toHaveBeenCalled()

    // Test Esc key to exit focus mode
    await fireEvent.keyDown(window, { key: 'Escape' })
    expect(onUpdateShow).toHaveBeenCalledWith(false)
  })

  it('loads and displays personal calendar subscription feed URL', async () => {
    apiMock.mockResolvedValueOnce({
      feed_url: '/api/calendar/signed-token-12345.ics',
      full_feed_url: 'http://localhost:8000/api/calendar/signed-token-12345.ics',
    })

    renderWithProviders(CalendarSubscriptionModal, {
      props: { show: true },
    })

    await waitFor(() => {
      expect(screen.getByLabelText('日历订阅链接')).toHaveValue(
        'http://localhost:8000/api/calendar/signed-token-12345.ics',
      )
    })
    expect(screen.getByRole('button', { name: '复制链接' })).toBeInTheDocument()
  })

  it('submits webhook notification card dispatch', async () => {
    const meeting = meetingFixture()
    apiMock.mockResolvedValueOnce({ status: 'dispatched' })

    const onUpdateShow = vi.fn()
    renderWithProviders(WebhookNotifyModal, {
      props: {
        show: true,
        meeting: meeting as any,
        'onUpdate:show': onUpdateShow,
      },
    })

    const input = screen.getByLabelText('Webhook 地址')
    await fireEvent.update(input, 'https://open.feishu.cn/open-apis/bot/v2/hook/xyz-token')

    await waitFor(() => {
      expect(screen.getByRole('button', { name: '立即推送' })).toBeEnabled()
    })

    const submitBtn = screen.getByRole('button', { name: '立即推送' })
    await fireEvent.click(submitBtn)

    await waitFor(() => {
      expect(apiMock).toHaveBeenCalledWith(
        '/api/meetings/m1/webhook-notify',
        expect.objectContaining({
          method: 'POST',
          body: JSON.stringify({
            platform: 'feishu',
            webhook_url: 'https://open.feishu.cn/open-apis/bot/v2/hook/xyz-token',
          }),
        }),
      )
    })
    expect(onUpdateShow).toHaveBeenCalledWith(false)
  })
})
