import { fireEvent, render, screen, waitFor } from '@testing-library/vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import ProjectDetailView from '../views/ProjectDetailView.vue'
import { session } from '../auth/session'

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

function defaultProjectResponse(path: string) {
  if (path === '/api/projects/p1') return Promise.resolve(project)
  if (path === '/api/attention') return Promise.resolve({ items: [], unread_count: 0, truncated: false })
  return Promise.resolve([])
}

describe('project workspace', () => {
  beforeEach(() => {
    apiMock.mockReset()
    session.user = { id: 'u1', username: 'lin', display_name: '林宇', role: 'member', status: 'active' }
    session.loaded = true
    apiMock.mockImplementation(defaultProjectResponse)
  })

  it('keeps overview focused on project state and actionable summaries', async () => {
    render(ProjectDetailView)
    expect(await screen.findByRole('heading', { name: 'MeetFlow' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: '项目状态' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: '下一次会议' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: '需要处理' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: '近期行动项' })).toBeInTheDocument()
    expect(screen.queryByLabelText('进展记录')).not.toBeInTheDocument()
    expect(screen.queryByTestId('project-inline-progress')).not.toBeInTheDocument()
  })

  it('places project progress editing and AI drafts in Activity', async () => {
    render(ProjectDetailView)
    await fireEvent.click(await screen.findByRole('tab', { name: '动态' }))
    expect(screen.getByLabelText('进展记录')).toBeInTheDocument()
    expect(screen.getByTestId('project-inline-progress')).toBeInTheDocument()
  })

  it('opens an action drawer from the global New menu', async () => {
    render(ProjectDetailView)
    await fireEvent.click(await screen.findByRole('button', { name: '新建' }))
    await fireEvent.click(screen.getByRole('menuitem', { name: '行动项' }))
    expect(screen.getByRole('dialog', { name: '添加行动项' })).toBeInTheDocument()
  })

  it('loads project actions in the Actions tab', async () => {
    apiMock.mockImplementation((path: string) => {
      if (path === '/api/actions?project_id=p1&status=open') {
        return Promise.resolve({ items: [{ id: 'a1', content: '确认范围', status: 'open', priority: 'high', owner_user_id: 'u1', due_date: '2026-07-25', meeting_id: 'm1' }], total: 1 })
      }
      return defaultProjectResponse(path)
    })

    render(ProjectDetailView)
    await fireEvent.click(await screen.findByRole('tab', { name: '行动项' }))
    expect(await screen.findByText('确认范围')).toBeInTheDocument()
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

  it('opens a project-scoped meeting drawer from Next meeting', async () => {
    render(ProjectDetailView)
    await screen.findByText('下一次会议')
    await fireEvent.click(screen.getByRole('button', { name: '添加会议' }))

    expect(screen.getByRole('dialog', { name: '添加会议' })).toBeInTheDocument()
    expect(screen.getByLabelText('会议标题')).toBeInTheDocument()
  })
})
