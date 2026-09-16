import { fireEvent, render, screen, waitFor, within } from '@testing-library/vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const apiMock = vi.hoisted(() => vi.fn())
vi.mock('../api/client', () => ({ api: apiMock }))

import MeetingCommentsPanel from '../components/MeetingCommentsPanel.vue'

const meeting = {
  id: 'm1',
  participants: [
    { user: { id: 'u1', username: 'lin', display_name: '林宇' }, participation_role: 'host', position: 0 },
  ],
} as any

function comment(overrides: Record<string, unknown> = {}) {
  return {
    id: 'c1',
    parent_id: null,
    body_markdown: '需要确认',
    version: 1,
    creator: { id: 'u1', username: 'lin', display_name: '林宇' },
    mentions: [],
    edited_at: null,
    deleted_at: null,
    created_at: '2026-07-24T02:00:00Z',
    replies: [],
    reply_next_cursor: null,
    resolved_at: null,
    resolved_by: null,
    can_edit: true,
    can_delete: true,
    can_resolve: true,
    ...overrides,
  }
}

function page(items: Record<string, unknown>[]) {
  return { items, next_cursor: null }
}

describe('meeting comments', () => {
  beforeEach(() => { apiMock.mockReset() })

  it('posts a reply then refreshes only the meeting comment thread', async () => {
    apiMock
      .mockResolvedValueOnce(page([comment()]))
      .mockResolvedValueOnce({ id: 'c2' })
      .mockResolvedValueOnce(page([]))
    render(MeetingCommentsPanel, { props: { meeting } })
    await screen.findByText('需要确认')
    await fireEvent.click(screen.getByRole('button', { name: '回复' }))
    await fireEvent.update(screen.getByRole('combobox', { name: '评论内容' }), '已确认')
    await fireEvent.click(screen.getByRole('button', { name: '发送评论' }))
    await waitFor(() => expect(apiMock).toHaveBeenCalledWith('/api/comments', expect.objectContaining({ method: 'POST' })))
    expect(apiMock).toHaveBeenCalledWith('/api/comments?target_type=meeting&target_id=m1&limit=20&reply_limit=3')
    expect(apiMock).not.toHaveBeenCalledWith('/api/meetings/m1')
  })

  it('shows edited and deleted states without write actions on a deleted comment', async () => {
    apiMock.mockResolvedValue(page([
      comment({ id: 'c1', body_markdown: '已更新内容', edited_at: '2026-07-24T03:00:00Z' }),
      comment({ id: 'c2', body_markdown: null, can_edit: false, can_delete: false, can_resolve: false }),
    ]))
    render(MeetingCommentsPanel, { props: { meeting } })

    expect(await screen.findByText('已更新内容')).toBeVisible()
    expect(screen.getByText('已编辑')).toBeVisible()
    const deleted = screen.getByText('评论已删除').closest('li')!
    expect(within(deleted).queryByRole('button', { name: '回复' })).not.toBeInTheDocument()
    expect(within(deleted).queryByRole('button', { name: '编辑' })).not.toBeInTheDocument()
    expect(within(deleted).queryByRole('button', { name: '删除' })).not.toBeInTheDocument()
  })

  it('deletes a comment after confirming in the popconfirm', async () => {
    apiMock
      .mockResolvedValueOnce(page([comment()]))
      .mockResolvedValueOnce(undefined)
      .mockResolvedValueOnce(page([]))
    render(MeetingCommentsPanel, { props: { meeting } })
    await screen.findByText('需要确认')

    await fireEvent.click(screen.getByRole('button', { name: '删除' }))
    expect(await screen.findByText('确定删除这条评论吗？')).toBeVisible()
    await fireEvent.click(screen.getByRole('button', { name: '确认' }))

    await waitFor(() => expect(apiMock).toHaveBeenCalledWith('/api/comments/c1', {
      method: 'DELETE',
      body: JSON.stringify({ expected_version: 1 }),
    }))
  })

  it('loads the remaining replies with the after cursor', async () => {
    const replies = [1, 2, 3].map((index) => comment({ id: `r${index}`, parent_id: 'c1', body_markdown: `回复 ${index}` }))
    apiMock
      .mockResolvedValueOnce(page([comment({ reply_count: 5, reply_next_cursor: 'r3', replies })]))
      .mockResolvedValueOnce(page([comment({ id: 'r4', parent_id: 'c1', body_markdown: '回复 4' }), comment({ id: 'r5', parent_id: 'c1', body_markdown: '回复 5' })]))
    render(MeetingCommentsPanel, { props: { meeting } })

    await screen.findByText('回复 1')
    await fireEvent.click(screen.getByRole('button', { name: '查看全部回复（5）' }))

    await waitFor(() => expect(apiMock).toHaveBeenCalledWith('/api/comments/c1/replies?limit=20&after=r3'))
    expect(await screen.findByText('回复 5')).toBeVisible()
    expect(screen.queryByRole('button', { name: /查看全部回复/ })).not.toBeInTheDocument()
  })

  it('renders mention badges under the comment body', async () => {
    apiMock.mockResolvedValue(page([comment({ mentions: [{ id: 'u2', username: 'qiao', display_name: '乔安' }] })]))
    render(MeetingCommentsPanel, { props: { meeting } })

    expect(await screen.findByText('@乔安')).toBeVisible()
  })
})
