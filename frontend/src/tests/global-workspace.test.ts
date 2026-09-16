import { fireEvent, render, screen, waitFor } from '@testing-library/vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { session } from '../auth/session'
import ActionsView from '../views/ActionsView.vue'
import DecisionsView from '../views/DecisionsView.vue'
import MeetingsView from '../views/MeetingsView.vue'
import { renderWithProviders } from './helpers'

const { apiMock, pushMock, routeState } = vi.hoisted(() => ({
  apiMock: vi.fn(),
  pushMock: vi.fn(),
  routeState: { query: {} as Record<string, unknown> },
}))
vi.mock('../api/client', () => ({ api: apiMock }))
vi.mock('vue-router', () => ({
  useRouter: () => ({ push: pushMock }),
  useRoute: () => ({ path: '/', query: routeState.query }),
  RouterLink: { props: ['to'], template: '<a :href="to"><slot /></a>' },
}))

const user = { id: 'u1', username: 'lin', display_name: '林宇', role: 'member' as const, status: 'active' as const }
const qiao = { id: 'u2', username: 'qiao', display_name: '乔一' }
const project = {
  id: 'p1',
  name: 'MeetFlow',
  slug: 'meetflow',
  status: 'active',
  health: 'on_track',
  memberships: [{ role: 'member', user }, { role: 'member', user: qiao }],
}

const actionRows = [
  { id: 'a1', project_id: 'p1', meeting_id: 'm1', content: '确认范围', owner_user_id: 'u1', due_date: '2026-07-25', priority: 'high', status: 'open', version: 3, is_derived: false, completed_at: null },
  { id: 'a2', project_id: 'p1', meeting_id: null, content: '整理纪要', owner_user_id: 'u9', due_date: null, priority: 'normal', status: 'in_progress', version: 2, is_derived: false, completed_at: null },
]

function mockActions(items: unknown[] = actionRows, total = items.length) {
  apiMock.mockImplementation((path: string, init?: RequestInit) => {
    if (path === '/api/projects') return Promise.resolve([project])
    if (path === '/api/actions/a1' && init?.method === 'PUT') return Promise.resolve({ id: 'a1' })
    if (path.startsWith('/api/actions?')) return Promise.resolve({ items, total, limit: 50, offset: 0 })
    return Promise.resolve({})
  })
}

function actionCalls() {
  return apiMock.mock.calls
    .map(([path]) => String(path))
    .filter((path) => path.startsWith('/api/actions?'))
}

describe('global workspace views', () => {
  beforeEach(() => {
    apiMock.mockReset()
    pushMock.mockReset()
    routeState.query = {}
    session.user = user
    session.loaded = true
    apiMock.mockImplementation((path: string) => path === '/api/projects'
      ? Promise.resolve([project])
      : Promise.resolve({ items: [], total: 0, limit: 50, offset: 0 }))
  })

  it('filters decisions by project and status', async () => {
    render(DecisionsView)
    await screen.findByRole('heading', { name: '决策日志' })
    await fireEvent.update(screen.getByLabelText('状态'), 'proposed')
    await fireEvent.update(screen.getByLabelText('项目'), 'p1')
    await waitFor(() => expect(apiMock).toHaveBeenCalledWith('/api/decisions?project_id=p1&status=proposed'))
  })

  it('shows actions assigned to the current user by default with server pagination', async () => {
    mockActions()

    renderWithProviders(ActionsView)
    await screen.findByText('确认范围')

    const first = actionCalls()[0]
    expect(first).toContain('limit=50&offset=0')
    expect(first).toContain('status=open')
    expect(first).toContain('owner_user_id=u1')
    expect(screen.getByLabelText('负责人')).toHaveValue('me')
    expect(document.querySelector('.n-data-table')).not.toBeNull()
  })

  it('renders aggregated member names and the id fallback in the owner column', async () => {
    mockActions()

    renderWithProviders(ActionsView)

    expect(await screen.findByText('林宇')).toBeInTheDocument()
    expect(screen.getByText('用户·u9')).toBeInTheDocument()
  })

  it('moves project and due filters into the server query', async () => {
    mockActions([], 0)
    renderWithProviders(ActionsView)
    await waitFor(() => expect(actionCalls().length).toBeGreaterThan(0))

    await fireEvent.update(screen.getByLabelText('项目'), 'p1')
    await waitFor(() => {
      const filtered = actionCalls().find((path) => path.includes('project_id=p1'))
      expect(filtered).toBeTruthy()
      expect(filtered).toContain('status=open')
      expect(filtered).toContain('owner_user_id=u1')
    })

    await fireEvent.update(screen.getByLabelText('期限'), 'overdue')
    await waitFor(() => expect(actionCalls().some((path) => path.includes('due_before='))).toBe(true))
  })

  it('requests the second page with offset 50', async () => {
    mockActions(actionRows, 120)
    renderWithProviders(ActionsView)
    await screen.findByText('确认范围')

    const pageTwo = await waitFor(() => {
      const item = [...document.querySelectorAll('.n-pagination-item')]
        .find((element) => element.textContent === '2')
      if (!item) throw new Error('page 2 is not rendered yet')
      return item as HTMLElement
    })
    await fireEvent.click(pageTwo)

    await waitFor(() => expect(actionCalls().some((path) => path.includes('offset=50'))).toBe(true))
  })

  it('highlights the deep-linked action row', async () => {
    routeState.query = { highlight: 'a1' }
    mockActions()

    renderWithProviders(ActionsView)

    await waitFor(() => {
      const row = document.querySelector('[data-row-key="a1"]')
      expect(row).not.toBeNull()
      expect(row).toHaveClass('action-row-highlight')
    })
  })

  it('edits an action through the shared drawer and reloads the list', async () => {
    mockActions()
    renderWithProviders(ActionsView)
    await screen.findByText('确认范围')

    await fireEvent.click(screen.getByRole('button', { name: '编辑行动项“确认范围”' }))
    expect(await screen.findByRole('heading', { name: '编辑行动项' })).toBeInTheDocument()
    await fireEvent.update(screen.getByLabelText('行动项内容'), '确认范围（更新）')
    await fireEvent.click(screen.getByRole('button', { name: '保存行动项' }))

    await waitFor(() => {
      const put = apiMock.mock.calls.find(([path, init]) => (
        path === '/api/actions/a1' && (init as RequestInit | undefined)?.method === 'PUT'
      ))
      expect(put).toBeTruthy()
      expect(JSON.parse(String((put![1] as RequestInit).body))).toMatchObject({
        content: '确认范围（更新）',
        expected_version: 3,
      })
    })
  })

  it('keeps derived actions read-only', async () => {
    mockActions([{
      ...actionRows[0],
      id: 'a3',
      content: '自动跟进',
      is_derived: true,
    }])
    renderWithProviders(ActionsView)
    await screen.findByText('自动跟进')

    expect(screen.getByText('由议题派生')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '编辑行动项“自动跟进”' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '开始行动项“自动跟进”' })).not.toBeInTheDocument()
  })

  it('creates a meeting through its project-scoped endpoint', async () => {
    apiMock.mockImplementation((path: string, init?: RequestInit) => {
      if (path === '/api/projects') return Promise.resolve([project])
      if (path.startsWith('/api/meetings?')) return Promise.resolve({ items: [], total: 0, limit: 50, offset: 0 })
      if (path === '/api/projects/p1/meetings' && init?.method === 'POST') return Promise.resolve({ id: 'm2' })
      return Promise.resolve({})
    })
    render(MeetingsView)
    await fireEvent.click(await screen.findByRole('button', { name: '新建会议' }))

    expect(await screen.findByLabelText('会议标题')).toBeVisible()
    await fireEvent.click(document.querySelector('.n-select .n-base-selection')!)
    const projectOption = await waitFor(() => {
      const option = [...document.querySelectorAll('.n-base-select-option__content')]
        .find((candidate) => candidate.textContent === 'MeetFlow')
      if (!option) throw new Error('project option is not open yet')
      return option
    })
    await fireEvent.click(projectOption)
    await fireEvent.update(screen.getByLabelText('会议标题'), '产品评审')
    await fireEvent.update(screen.getByLabelText('开始时间'), '2026-07-24T10:00')
    await fireEvent.update(screen.getByLabelText('结束时间'), '2026-07-24T11:00')
    await fireEvent.click(screen.getByRole('button', { name: '创建会议' }))

    await waitFor(() => expect(apiMock).toHaveBeenCalledWith('/api/projects/p1/meetings', expect.objectContaining({ method: 'POST' })))
    const postCall = apiMock.mock.calls.find(([path, init]) => (
      path === '/api/projects/p1/meetings' && (init as RequestInit | undefined)?.method === 'POST'
    ))
    const payload = JSON.parse((postCall?.[1] as RequestInit).body as string)
    expect(payload.participants).toContainEqual({ user_id: 'u1', participation_role: 'host' })
    expect(payload.scheduled_start).toMatch(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$/)
    expect(payload.scheduled_end).toMatch(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$/)
    expect(new Date(payload.scheduled_start).getTime()).toBeLessThan(new Date(payload.scheduled_end).getTime())
    await waitFor(() => expect(pushMock).toHaveBeenCalledWith('/meetings/m2'))
  })

  it('rejects a whitespace-only meeting title before calling the API', async () => {
    apiMock.mockImplementation((path: string) => {
      if (path === '/api/projects') return Promise.resolve([project])
      if (path.startsWith('/api/meetings?')) return Promise.resolve({ items: [], total: 0, limit: 50, offset: 0 })
      return Promise.resolve({})
    })
    render(MeetingsView)
    await fireEvent.click(await screen.findByRole('button', { name: '新建会议' }))

    await fireEvent.update(await screen.findByLabelText('会议标题'), '   ')
    await fireEvent.update(screen.getByLabelText('开始时间'), '2026-07-24T10:00')
    await fireEvent.update(screen.getByLabelText('结束时间'), '2026-07-24T11:00')
    await fireEvent.click(screen.getByRole('button', { name: '创建会议' }))

    expect(await screen.findByText('请输入会议标题')).toBeInTheDocument()
    const posted = apiMock.mock.calls.some(([path, init]) => (
      path === '/api/projects/p1/meetings' && (init as RequestInit | undefined)?.method === 'POST'
    ))
    expect(posted).toBe(false)
  })
})
