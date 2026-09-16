import { fireEvent, render, screen, waitFor } from '@testing-library/vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import MeetingsView from '../views/MeetingsView.vue'

const { apiMock, pushMock } = vi.hoisted(() => ({ apiMock: vi.fn(), pushMock: vi.fn() }))

vi.mock('../api/client', () => ({ api: apiMock }))
vi.mock('../auth/session', () => ({ session: { user: { id: 'u1', username: 'lin', display_name: '林宇' } } }))
vi.mock('vue-router', () => ({
  RouterLink: { props: ['to'], template: '<a :href="to"><slot /></a>' },
  useRouter: () => ({ push: pushMock }),
}))

const project = {
  id: 'p1',
  name: '平台',
  slug: 'platform',
  memberships: [
    { role: 'member', user: { id: 'u1', username: 'lin', display_name: '林宇' } },
    { role: 'member', user: { id: 'u2', username: 'chen', display_name: '陈晨' } },
  ],
}
const meetings = [
  { id: 'm1', project: { id: 'p1', name: '平台' }, series: { id: 's1', title: '产品周会' }, occurrence_kind: 'scheduled', title: '产品周会 · 第 1 次', purpose_markdown: '', scheduled_start: '2026-08-03T01:00:00Z', scheduled_end: '2026-08-03T02:00:00Z', status: 'ready', host: null, agenda_count: 0, snapshot_count: 0, amendment_count: 0 },
  { id: 'm2', project: { id: 'p1', name: '平台' }, series: null, occurrence_kind: 'manual', title: '临时评审', purpose_markdown: '', scheduled_start: '2026-08-04T01:00:00Z', scheduled_end: '2026-08-04T02:00:00Z', status: 'completed', host: null, agenda_count: 0, snapshot_count: 1, amendment_count: 0 },
  { id: 'm3', project: { id: 'p1', name: '平台' }, series: null, occurrence_kind: 'manual', title: '已取消的评审', purpose_markdown: '', scheduled_start: '2026-08-05T01:00:00Z', scheduled_end: '2026-08-05T02:00:00Z', status: 'canceled', host: null, agenda_count: 0, snapshot_count: 0, amendment_count: 0 },
]

function page(items: typeof meetings, total = items.length) {
  return { items, total, limit: 50, offset: 0 }
}

function renderList(search = '') {
  window.history.replaceState(null, '', `/meetings${search}`)
  apiMock.mockImplementation((path: string) => {
    if (path === '/api/projects') return Promise.resolve([project])
    if (path.includes('status=completed')) return Promise.resolve(page([meetings[1]], 1))
    if (path.includes('status=canceled')) return Promise.resolve(page([meetings[2]], 1))
    return Promise.resolve(page(meetings))
  })
  return render(MeetingsView)
}

async function pickNow(label: RegExp) {
  const control = screen.getByLabelText(label)
  const input = (control.tagName === 'INPUT' ? control : control.querySelector('input')) as HTMLInputElement
  await fireEvent.focus(input)
  // MeetingsView tests render without the zhCN provider, so match both locales.
  const nowButtons = await screen.findAllByText(/^(此刻|Now)$/)
  await fireEvent.click(nowButtons[nowButtons.length - 1])
}

describe('meeting list advanced search', () => {
  beforeEach(() => {
    apiMock.mockReset()
    pushMock.mockReset()
  })

  it('keeps advanced filters discoverable and reveals all fields on demand', async () => {
    renderList()

    const button = await screen.findByRole('button', { name: '高级筛选' })
    expect(button).toHaveAttribute('aria-expanded', 'false')
    expect(screen.queryByLabelText('会议系列')).not.toBeInTheDocument()

    await fireEvent.click(button)

    expect(button).toHaveAttribute('aria-expanded', 'true')
    expect(screen.getByLabelText('项目')).toBeVisible()
    expect(screen.getByLabelText('会议系列')).toBeVisible()
    expect(screen.getByLabelText('会议状态')).toBeVisible()
    expect(screen.getByLabelText('参与者')).toBeVisible()
  })

  it('filters by status on the server and exposes the active filter count', async () => {
    renderList()
    await fireEvent.click(await screen.findByRole('button', { name: '高级筛选' }))
    await fireEvent.update(screen.getByLabelText('会议状态'), 'completed')

    expect(screen.getByRole('button', { name: '高级筛选（已启用 1 项）' })).toHaveClass('is-active')
    await waitFor(() => expect(apiMock).toHaveBeenCalledWith(expect.stringContaining('status=completed')))
    expect(await screen.findByText('已加载 1 / 共 1 场会议')).toBeVisible()
    expect(screen.getByText('搜索与系列筛选仅作用于已加载页')).toBeVisible()
    expect(screen.getByText('临时评审')).toBeVisible()
    expect(screen.queryByText('产品周会 · 第 1 次')).not.toBeInTheDocument()
  })

  it('renders canceled meetings when 已取消 is selected', async () => {
    renderList()
    await fireEvent.click(await screen.findByRole('button', { name: '高级筛选' }))
    await fireEvent.update(screen.getByLabelText('会议状态'), 'canceled')

    await waitFor(() => expect(apiMock).toHaveBeenCalledWith(expect.stringContaining('status=canceled')))
    expect(await screen.findByText('已取消的评审')).toBeVisible()
  })

  it('loads more meetings with the loaded-length offset and reports the loaded range', async () => {
    apiMock.mockImplementation((path: string) => {
      if (path === '/api/projects') return Promise.resolve([project])
      if (path.includes('offset=1')) return Promise.resolve({ items: [meetings[1], meetings[2]], total: 3, limit: 50, offset: 1 })
      return Promise.resolve(page([meetings[0]], 3))
    })

    render(MeetingsView)
    expect(await screen.findByText('产品周会 · 第 1 次')).toBeVisible()

    await fireEvent.click(screen.getByRole('button', { name: '高级筛选' }))
    expect(screen.getByText('已加载 1 / 共 3 场会议')).toBeVisible()
    expect(screen.getByText('搜索与系列筛选仅作用于已加载页')).toBeVisible()

    await fireEvent.click(screen.getByRole('button', { name: '加载更多' }))

    expect(await screen.findByText('临时评审')).toBeVisible()
    expect(screen.getByText('已加载 3 / 共 3 场会议')).toBeVisible()
    expect(screen.queryByRole('button', { name: '加载更多' })).not.toBeInTheDocument()
    await waitFor(() => expect(apiMock).toHaveBeenCalledWith(expect.stringContaining('offset=1')))
    expect(apiMock.mock.calls.filter(([path]) => path === '/api/projects')).toHaveLength(1)
  })

  it('wires every server-side filter into the meetings request', async () => {
    renderList()
    await waitFor(() => expect(apiMock).toHaveBeenCalledWith('/api/meetings?limit=50&offset=0'))

    await fireEvent.click(await screen.findByRole('button', { name: '高级筛选' }))
    await fireEvent.update(screen.getByLabelText('项目'), 'p1')
    await waitFor(() => expect(apiMock).toHaveBeenCalledWith(expect.stringContaining('project_id=p1')))

    await fireEvent.update(screen.getByLabelText('参与者'), 'u2')
    await waitFor(() => expect(apiMock).toHaveBeenCalledWith(expect.stringContaining('participant_user_id=u2')))

    await pickNow(/开始时间不早于/)
    await waitFor(() => expect(apiMock).toHaveBeenCalledWith(expect.stringMatching(/start_after=\d{4}-\d{2}-\d{2}T/)))

    await pickNow(/开始时间不晚于/)
    await waitFor(() => expect(apiMock).toHaveBeenCalledWith(expect.stringMatching(/start_before=\d{4}-\d{2}-\d{2}T/)))
  })

  it('opens and highlights the series filter from the shared series URL, then clears it', async () => {
    renderList('?series_id=s1')

    expect(await screen.findByText('已启用 1 项')).toBeVisible()
    expect(screen.getByLabelText('会议系列')).toHaveValue('s1')

    await fireEvent.click(screen.getByRole('button', { name: '清除全部高级筛选' }))

    await waitFor(() => expect(window.location.search).toBe(''))
    expect(screen.getByLabelText('会议系列')).toHaveValue('')
  })
})
