import { fireEvent, render, screen, waitFor } from '@testing-library/vue'
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

describe('meeting comments', () => {
  beforeEach(() => apiMock.mockReset())

  it('posts a reply then refreshes only the meeting comment thread', async () => {
    apiMock
      .mockResolvedValueOnce({ items: [{ id: 'c1', body_markdown: '需要确认', version: 1, creator: { display_name: '林宇' }, replies: [], resolved_at: null, can_resolve: true, can_edit: true }] })
      .mockResolvedValueOnce({ id: 'c2' })
      .mockResolvedValueOnce({ items: [] })
    render(MeetingCommentsPanel, { props: { meeting } })
    await screen.findByText('需要确认')
    await fireEvent.click(screen.getByRole('button', { name: '回复' }))
    await fireEvent.update(screen.getByRole('combobox', { name: '评论内容' }), '已确认')
    await fireEvent.click(screen.getByRole('button', { name: '发送评论' }))
    await waitFor(() => expect(apiMock).toHaveBeenCalledWith('/api/comments', expect.objectContaining({ method: 'POST' })))
    expect(apiMock).toHaveBeenCalledWith('/api/comments?target_type=meeting&target_id=m1')
    expect(apiMock).not.toHaveBeenCalledWith('/api/meetings/m1')
  })
})
