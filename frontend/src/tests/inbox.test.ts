import { fireEvent, render, screen, waitFor } from '@testing-library/vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import InboxView from '../views/InboxView.vue'

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

describe('inbox view', () => {
  beforeEach(() => apiMock.mockReset())

  it('renders notifications with translated kinds and marks read ones', async () => {
    apiMock.mockResolvedValue({
      items: [
        notification(),
        notification({
          id: 2,
          kind: 'action.assigned',
          subject: { type: 'action_item', id: 'a1' },
          read_at: '2026-08-09T03:00:00Z',
        }),
      ],
      next_cursor: null,
      unread_count: 1,
    })
    render(InboxView, { global: { stubs: { RouterLink } } })

    expect(await screen.findByText('陈晨 · 提到了你 · 决策')).toBeInTheDocument()
    expect(screen.getByText('陈晨 · 分配了行动项给你 · 行动项')).toBeInTheDocument()
    expect(screen.getAllByText(/已读/).length).toBeGreaterThanOrEqual(2)
    expect(screen.getByRole('button', { name: '全部已读' })).toBeEnabled()
  })

  it('loads more pages with the next cursor', async () => {
    apiMock.mockResolvedValueOnce({
      items: [notification()],
      next_cursor: 5,
      unread_count: 2,
    })
    apiMock.mockResolvedValueOnce({
      items: [notification({ id: 2, kind: 'comment.reply', subject: { type: 'meeting', id: 'm1' } })],
      next_cursor: null,
      unread_count: 0,
    })
    render(InboxView, { global: { stubs: { RouterLink } } })

    await screen.findByText('陈晨 · 提到了你 · 决策')
    fireEvent.click(screen.getByRole('button', { name: '加载更多' }))

    await waitFor(() => {
      expect(apiMock).toHaveBeenCalledWith('/api/inbox?before=5')
      expect(screen.getByText('陈晨 · 回复了你 · 会议')).toBeInTheDocument()
    })
  })

  it('marks everything read', async () => {
    apiMock.mockResolvedValueOnce({ items: [notification()], next_cursor: null, unread_count: 1 })
    apiMock.mockResolvedValueOnce(undefined)
    render(InboxView, { global: { stubs: { RouterLink } } })

    const button = await screen.findByRole('button', { name: '全部已读' })
    fireEvent.click(button)

    await waitFor(() => {
      expect(apiMock).toHaveBeenCalledWith('/api/inbox/read-all', { method: 'POST' })
      expect(button).toBeDisabled()
    })
  })
})
