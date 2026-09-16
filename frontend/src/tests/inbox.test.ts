import { fireEvent, screen, waitFor } from '@testing-library/vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import InboxView from '../views/InboxView.vue'
import { renderWithProviders } from './helpers'

const { apiMock } = vi.hoisted(() => ({ apiMock: vi.fn() }))
vi.mock('../api/client', () => ({ api: apiMock }))

const RouterLink = { props: ['to'], template: '<a :href="to"><slot /></a>' }

const notification = (overrides = {}) => ({
  id: 1,
  actor: { id: 'u2', username: 'chen', display_name: '陈晨' },
  kind: 'comment.mention',
  subject: { type: 'decision', id: 'd1' },
  project: { id: 'p1' },
  meeting: null,
  source_comment: { id: 'c1' },
  data: {},
  read_at: null,
  created_at: '2026-08-09T02:00:00Z',
  ...overrides,
})

type MockOptions = {
  items?: unknown[]
  historyNextCursor?: number | null
  moreItems?: unknown[]
  moreNextCursor?: number | null
  unreadCount?: number
  changes?: unknown[]
  changesNextCursor?: number
  changesHasMore?: boolean
}

function mockApi(options: MockOptions = {}) {
  apiMock.mockImplementation((path: string) => {
    if (path.startsWith('/api/inbox/changes')) {
      return Promise.resolve({
        notifications: options.changes ?? [],
        next_cursor: options.changesNextCursor ?? 0,
        has_more: options.changesHasMore ?? false,
        unread_count: options.unreadCount ?? 0,
      })
    }
    if (path === '/api/inbox' || path.startsWith('/api/inbox?')) {
      const more = path.includes('before=')
      return Promise.resolve({
        items: more ? (options.moreItems ?? []) : (options.items ?? []),
        next_cursor: more ? (options.moreNextCursor ?? null) : (options.historyNextCursor ?? null),
        unread_count: options.unreadCount ?? 0,
      })
    }
    return Promise.resolve(undefined)
  })
}

function changesCalls() {
  return apiMock.mock.calls
    .map(([path]) => String(path))
    .filter((path) => path.startsWith('/api/inbox/changes'))
}

describe('inbox view', () => {
  beforeEach(() => {
    apiMock.mockReset()
  })

  it('renders notifications with translated kinds and marks read ones', async () => {
    mockApi({
      items: [
        notification(),
        notification({
          id: 2,
          kind: 'action.assigned',
          subject: { type: 'action_item', id: 'a1' },
          read_at: '2026-08-09T03:00:00Z',
        }),
      ],
      unreadCount: 1,
    })
    renderWithProviders(InboxView, { global: { stubs: { RouterLink } } })

    expect(await screen.findByText('陈晨 · 提到了你 · 决策')).toBeInTheDocument()
    expect(screen.getByText('陈晨 · 分配了行动项给你 · 行动项')).toBeInTheDocument()
    expect(screen.getAllByText(/已读/).length).toBeGreaterThanOrEqual(2)
    expect(screen.getByRole('button', { name: '全部已读' })).toBeEnabled()
  })

  it('shows unread rows with the data-unread marker', async () => {
    mockApi({
      items: [
        notification(),
        notification({ id: 2, kind: 'action.assigned', subject: { type: 'action_item', id: 'a1' }, read_at: '2026-08-09T03:00:00Z' }),
      ],
      unreadCount: 1,
    })
    renderWithProviders(InboxView, { global: { stubs: { RouterLink } } })

    const unreadRow = (await screen.findByText('陈晨 · 提到了你 · 决策')).closest('.n-list-item')
    const readRow = screen.getByText('陈晨 · 分配了行动项给你 · 行动项').closest('.n-list-item')
    expect(unreadRow).toHaveAttribute('data-unread', 'true')
    expect(readRow).toHaveAttribute('data-unread', 'false')
  })

  it('loads more pages with the next cursor', async () => {
    mockApi({
      items: [notification()],
      historyNextCursor: 5,
      unreadCount: 2,
      moreItems: [notification({ id: 2, kind: 'comment.reply', subject: { type: 'meeting', id: 'm1' } })],
    })
    renderWithProviders(InboxView, { global: { stubs: { RouterLink } } })

    await screen.findByText('陈晨 · 提到了你 · 决策')
    fireEvent.click(screen.getByRole('button', { name: '加载更多' }))

    await waitFor(() => {
      expect(apiMock).toHaveBeenCalledWith('/api/inbox?before=5')
      expect(screen.getByText('陈晨 · 回复了你 · 会议')).toBeInTheDocument()
    })
  })

  it('links mentions to the meeting comment and falls back to the subject deep link', async () => {
    mockApi({
      items: [
        notification({ id: 1, meeting: { id: 'm1' }, source_comment: { id: 'c1' } }),
        notification({
          id: 2,
          kind: 'comment.reply',
          subject: { type: 'decision', id: 'd1' },
          meeting: null,
          source_comment: null,
        }),
      ],
      unreadCount: 2,
    })
    renderWithProviders(InboxView, { global: { stubs: { RouterLink } } })

    await screen.findByText('陈晨 · 提到了你 · 决策')

    expect(document.querySelector('a[href="/meetings/m1?comment=c1"]')).not.toBeNull()
    expect(document.querySelector('a[href="/decisions?highlight=d1"]')).not.toBeNull()
  })

  it('pulls incremental notifications on mount, prepends them, and dedupes by id', async () => {
    mockApi({
      items: [
        notification({ id: 5 }),
        notification({ id: 4, kind: 'action.assigned', subject: { type: 'action_item', id: 'a1' } }),
      ],
      unreadCount: 2,
      changes: [
        notification({ id: 6, kind: 'comment.reply', subject: { type: 'meeting', id: 'm1' } }),
        notification({ id: 5 }),
        notification({ id: 7, kind: 'decision.review_requested', subject: { type: 'decision', id: 'd2' } }),
      ],
      changesNextCursor: 7,
    })
    renderWithProviders(InboxView, { global: { stubs: { RouterLink } } })

    await waitFor(() => expect(apiMock).toHaveBeenCalledWith('/api/inbox/changes?cursor=4&limit=50'))
    expect(await screen.findByText('陈晨 · 回复了你 · 会议')).toBeInTheDocument()
    expect(screen.getAllByText('陈晨 · 提到了你 · 决策')).toHaveLength(1)
    expect(document.querySelector('.n-list-item')?.textContent).toContain('请求你评审决策')
  })

  it('shows the view-all hint when the incremental batch is truncated', async () => {
    mockApi({
      items: [notification()],
      changes: [notification({ id: 9, kind: 'comment.reply', subject: { type: 'meeting', id: 'm1' } })],
      changesNextCursor: 9,
      changesHasMore: true,
    })
    renderWithProviders(InboxView, { global: { stubs: { RouterLink } } })

    expect(await screen.findByText('点击刷新查看全部')).toBeInTheDocument()
  })

  it('refreshes the increment when the page becomes visible again', async () => {
    mockApi({ items: [notification()], unreadCount: 1 })
    renderWithProviders(InboxView, { global: { stubs: { RouterLink } } })

    await waitFor(() => expect(changesCalls().length).toBe(1))

    Object.defineProperty(document, 'visibilityState', { value: 'visible', configurable: true })
    document.dispatchEvent(new Event('visibilitychange'))

    await waitFor(() => expect(changesCalls().length).toBe(2))
  })

  it('marks a notification read and refreshes the shell badge', async () => {
    mockApi({ items: [notification()], unreadCount: 1 })
    renderWithProviders(InboxView, { global: { stubs: { RouterLink } } })

    await screen.findByText('陈晨 · 提到了你 · 决策')
    await fireEvent.click(document.querySelector('.n-list-item')!)

    await waitFor(() => {
      expect(apiMock).toHaveBeenCalledWith('/api/inbox/1/read', { method: 'POST' })
      // Shell badge refresh, distinct from the page's incremental `cursor=<id>&limit=50` request.
      expect(apiMock).toHaveBeenCalledWith('/api/inbox/changes?cursor=0&limit=1')
    })
  })

  it('marks everything read and refreshes the shell badge', async () => {
    mockApi({ items: [notification()], unreadCount: 1 })
    renderWithProviders(InboxView, { global: { stubs: { RouterLink } } })

    await screen.findByText('陈晨 · 提到了你 · 决策')
    const button = screen.getByRole('button', { name: '全部已读' })
    expect(button).toBeEnabled()
    fireEvent.click(button)

    await waitFor(() => {
      expect(apiMock).toHaveBeenCalledWith('/api/inbox/read-all', { method: 'POST' })
      expect(apiMock).toHaveBeenCalledWith('/api/inbox/changes?cursor=0&limit=1')
      expect(button).toBeDisabled()
    })
  })
})
