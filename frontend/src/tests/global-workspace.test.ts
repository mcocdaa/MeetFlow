import { fireEvent, render, screen, waitFor } from '@testing-library/vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { session } from '../auth/session'
import ActionsView from '../views/ActionsView.vue'
import DecisionsView from '../views/DecisionsView.vue'
import MeetingsView from '../views/MeetingsView.vue'

const { apiMock, pushMock } = vi.hoisted(() => ({ apiMock: vi.fn(), pushMock: vi.fn() }))
vi.mock('../api/client', () => ({ api: apiMock }))
vi.mock('vue-router', () => ({
  useRouter: () => ({ push: pushMock }),
  RouterLink: { props: ['to'], template: '<a :href="to"><slot /></a>' },
}))

const user = { id: 'u1', username: 'lin', display_name: '林宇', role: 'member' as const, status: 'active' as const }
const project = { id: 'p1', name: 'MeetFlow', slug: 'meetflow', status: 'active', health: 'on_track', memberships: [] }

describe('global workspace views', () => {
  beforeEach(() => {
    apiMock.mockReset()
    pushMock.mockReset()
    session.user = user
    session.loaded = true
    apiMock.mockImplementation((path: string) => path === '/api/projects' ? Promise.resolve([project]) : Promise.resolve({ items: [], total: 0, limit: 50, offset: 0 }))
  })

  it('filters decisions by project and status', async () => {
    render(DecisionsView)
    await screen.findByRole('heading', { name: '决策日志' })
    await fireEvent.update(screen.getByLabelText('状态'), 'proposed')
    await fireEvent.update(screen.getByLabelText('项目'), 'p1')
    await waitFor(() => expect(apiMock).toHaveBeenCalledWith('/api/decisions?project_id=p1&status=proposed'))
  })

  it('shows actions assigned to the current user by default', async () => {
    render(ActionsView)
    await waitFor(() => expect(apiMock).toHaveBeenCalledWith('/api/actions?status=open&owner_user_id=u1'))
    expect(screen.getByLabelText('负责人')).toHaveValue('me')
  })

  it('creates a meeting through its project-scoped endpoint', async () => {
    apiMock.mockImplementation((path: string, init?: RequestInit) => {
      if (path === '/api/projects') return Promise.resolve([project])
      if (path === '/api/meetings') return Promise.resolve({ items: [], total: 0, limit: 50, offset: 0 })
      if (path === '/api/projects/p1/meetings' && init?.method === 'POST') return Promise.resolve({ id: 'm2' })
      return Promise.resolve({})
    })
    render(MeetingsView)
    await fireEvent.click(await screen.findByRole('button', { name: '新建会议' }))
    await fireEvent.update(screen.getByLabelText('所属项目'), 'p1')
    await fireEvent.update(screen.getByLabelText('会议标题'), '产品评审')
    await fireEvent.update(screen.getByLabelText('开始时间'), '2026-07-24T10:00')
    await fireEvent.update(screen.getByLabelText('结束时间'), '2026-07-24T11:00')
    await fireEvent.click(screen.getByRole('button', { name: '创建会议' }))
    await waitFor(() => expect(apiMock).toHaveBeenCalledWith('/api/projects/p1/meetings', expect.objectContaining({ method: 'POST' })))
    expect(pushMock).toHaveBeenCalledWith('/meetings/m2')
  })
})
