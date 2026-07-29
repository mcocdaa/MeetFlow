import { fireEvent, render, screen, waitFor } from '@testing-library/vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import HomeView from '../views/HomeView.vue'
import ProjectsView from '../views/ProjectsView.vue'
import { session } from '../auth/session'
import { registerEditorAssistant } from '../plugins/registry'

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

  it('opens the project update editor when the AI work brief assistant is available', async () => {
    apiMock.mockResolvedValue({ items: [], unread_count: 0, truncated: false })
    registerEditorAssistant('project-update-editor', { template: '<div />' })

    render(HomeView, { global: { stubs: { RouterLink } } })

    expect(await screen.findByText('已启用')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: '生成项目简报' })).toHaveAttribute('href', '/projects')
    expect(screen.queryByText('尚未启用')).not.toBeInTheDocument()
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

  it('normalizes a project identifier without showing format instructions', async () => {
    session.user = { id: 'u1', username: 'lin', display_name: '林宇', role: 'member', status: 'active' }
    session.loaded = true
    apiMock.mockResolvedValue([])
    render(ProjectsView, { global: { stubs: { RouterLink } } })
    await screen.findByRole('button', { name: '新建项目' })
    await fireEvent.click(screen.getByRole('button', { name: '新建项目' }))
    const identifier = screen.getByLabelText('项目标识') as HTMLInputElement
    await fireEvent.update(identifier, 'Meet Flow_Test')

    expect(identifier.value).toBe('meet-flow-test')
    expect(identifier.pattern).toBe('')
    expect(screen.queryByText('仅使用小写字母、数字和连字符，例如 meetflow。')).not.toBeInTheDocument()
  })
})
