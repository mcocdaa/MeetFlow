import { fireEvent, render, screen, waitFor } from '@testing-library/vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import HomeView from '../views/HomeView.vue'
import ProjectsView from '../views/ProjectsView.vue'

const { apiMock } = vi.hoisted(() => ({ apiMock: vi.fn() }))
vi.mock('../api/client', () => ({ api: apiMock }))

const RouterLink = { props: ['to'], template: '<a :href="to"><slot /></a>' }

describe('personal workspace home', () => {
  beforeEach(() => apiMock.mockReset())

  it('renders one prioritized subject with translated, coalesced reasons', async () => {
    apiMock.mockResolvedValue({
      items: [{
        subject_type: 'action', subject_id: 'a1', title: '测试 reward',
        project: { id: 'p1', name: '训练平台', slug: 'training' },
        reasons: ['action_overdue', 'comment_reply'], due_date: '2026-07-20', status: 'open',
      }],
      notifications: [], mentions: [], unread_count: 0, truncated: false,
    })
    render(HomeView, { global: { stubs: { RouterLink } } })

    expect(await screen.findByText('测试 reward')).toBeInTheDocument()
    expect(screen.getByText('已逾期 · 有新回复')).toBeInTheDocument()
    expect(screen.queryByText('会议不是终点')).not.toBeInTheDocument()
  })

  it('filters the project list without hiding project context', async () => {
    apiMock.mockResolvedValue([
      { id: 'p1', name: 'MeetFlow', slug: 'meetflow', summary: '会议工作区', status: 'active', health: 'on_track', lead: { id: 'u1', username: 'lin', display_name: '林宇' }, target_date: '2026-08-01', memberships: [], updates: [], version: 1 },
      { id: 'p2', name: '旧项目', slug: 'legacy', summary: '', status: 'paused', health: 'at_risk', lead: null, target_date: null, memberships: [], updates: [], version: 1 },
    ])
    render(ProjectsView, { global: { stubs: { RouterLink } } })

    expect(await screen.findByText('MeetFlow')).toBeInTheDocument()
    await fireEvent.update(screen.getByLabelText('项目状态'), 'paused')
    await waitFor(() => expect(screen.queryByText('MeetFlow')).not.toBeInTheDocument())
    expect(screen.getByText('旧项目')).toBeInTheDocument()
  })
})
