import { fireEvent, render, screen, waitFor } from '@testing-library/vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import ProjectDetailView from '../views/ProjectDetailView.vue'

const { apiMock } = vi.hoisted(() => ({ apiMock: vi.fn() }))
vi.mock('../api/client', () => ({ api: apiMock }))
vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { id: 'p1' } }),
  RouterLink: { props: ['to'], template: '<a :href="to"><slot /></a>' },
}))

const project = {
  id: 'p1', name: 'MeetFlow', slug: 'meetflow', summary: '团队会议工作区', description_markdown: '项目说明',
  status: 'active', health: 'on_track', lead: { id: 'u1', username: 'lin', display_name: '林宇' }, target_date: '2026-08-01', version: 3,
  memberships: [{ role: 'member', user: { id: 'u1', username: 'lin', display_name: '林宇' } }],
  updates: [{ id: 'up1', project_id: 'p1', health: 'on_track', content_markdown: '完成后端契约', source: 'human', created_by: { id: 'u1', username: 'lin', display_name: '林宇' }, created_at: '2026-07-22T10:00:00Z', updated_at: '2026-07-22T10:00:00Z' }],
  next_meeting: { id: 'm1', title: '迭代评审', scheduled_start: '2026-07-24T02:00:00Z', status: 'ready' },
  recent_decisions: [{ id: 'd1', title: '采用项目工作区', status: 'final' }],
  meeting_count: 4, decision_count: 2, open_action_count: 3, series_summaries: [], attachments: [],
  created_by: { id: 'u1', username: 'lin', display_name: '林宇' }, updated_by: { id: 'u1', username: 'lin', display_name: '林宇' }, created_at: '', updated_at: '',
}

describe('project workspace', () => {
  beforeEach(() => {
    apiMock.mockReset()
    apiMock.mockImplementation((path: string) => {
      if (path === '/api/projects/p1') return Promise.resolve(project)
      if (path === '/api/attention') return Promise.resolve({ items: [], unread_count: 0, truncated: false })
      return Promise.resolve([])
    })
  })

  it('shows project context before compact metrics', async () => {
    render(ProjectDetailView)
    expect(await screen.findByRole('heading', { name: 'MeetFlow' })).toBeInTheDocument()
    expect(screen.getByText('需要关注')).toBeInTheDocument()
    expect(screen.getByText('下一次会议')).toBeInTheDocument()
    expect(screen.getByText('最近决策')).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: '动态' })).toBeInTheDocument()
  })

  it('appends a human progress update and reloads authoritative data', async () => {
    render(ProjectDetailView)
    await screen.findByText('完成后端契约')
    await fireEvent.update(screen.getByLabelText('进展记录'), '完成 1.0 前端壳层')
    await fireEvent.click(screen.getByRole('button', { name: '发布进展' }))
    await waitFor(() => expect(apiMock).toHaveBeenCalledWith('/api/projects/p1/updates', expect.objectContaining({
      method: 'POST', body: JSON.stringify({ health: 'on_track', content_markdown: '完成 1.0 前端壳层', source: 'human' }),
    })))
    expect(apiMock).toHaveBeenCalledWith('/api/projects/p1')
  })
})
