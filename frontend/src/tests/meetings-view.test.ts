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

const project = { id: 'p1', name: '平台', slug: 'platform' }
const meetings = [
  { id: 'm1', project, series: { id: 's1', title: '产品周会' }, occurrence_kind: 'scheduled', title: '产品周会 · 第 1 次', purpose_markdown: '', scheduled_start: '2026-08-03T01:00:00Z', scheduled_end: '2026-08-03T02:00:00Z', status: 'ready', host: null, agenda_count: 0, snapshot_count: 0, amendment_count: 0 },
  { id: 'm2', project, series: null, occurrence_kind: 'manual', title: '临时评审', purpose_markdown: '', scheduled_start: '2026-08-04T01:00:00Z', scheduled_end: '2026-08-04T02:00:00Z', status: 'completed', host: null, agenda_count: 0, snapshot_count: 1, amendment_count: 0 },
  { id: 'm3', project, series: null, occurrence_kind: 'manual', title: '已取消的评审', purpose_markdown: '', scheduled_start: '2026-08-05T01:00:00Z', scheduled_end: '2026-08-05T02:00:00Z', status: 'canceled', host: null, agenda_count: 0, snapshot_count: 0, amendment_count: 0 },
]

function renderList(search = '') {
  window.history.replaceState(null, '', `/meetings${search}`)
  apiMock.mockImplementation((path: string) => Promise.resolve(path === '/api/projects' ? [project] : { items: meetings }))
  return render(MeetingsView)
}

describe('meeting list advanced search', () => {
  beforeEach(() => { apiMock.mockReset(); pushMock.mockReset() })

  it('keeps advanced filters discoverable and reveals all three fields on demand', async () => {
    renderList()

    const button = await screen.findByRole('button', { name: '高级筛选' })
    expect(button).toHaveAttribute('aria-expanded', 'false')
    expect(screen.queryByLabelText('会议系列')).not.toBeInTheDocument()

    await fireEvent.click(button)

    expect(button).toHaveAttribute('aria-expanded', 'true')
    expect(screen.getByLabelText('项目')).toBeVisible()
    expect(screen.getByLabelText('会议系列')).toBeVisible()
    expect(screen.getByLabelText('会议状态')).toBeVisible()
  })

  it('filters by status and exposes the active filter count', async () => {
    renderList()
    await fireEvent.click(await screen.findByRole('button', { name: '高级筛选' }))
    await fireEvent.update(screen.getByLabelText('会议状态'), 'completed')

    expect(screen.getByRole('button', { name: '高级筛选（已启用 1 项）' })).toHaveClass('is-active')
    expect(screen.getByText('当前显示 1 场会议。')).toBeVisible()
    expect(screen.getByText('临时评审')).toBeVisible()
    expect(screen.queryByText('产品周会 · 第 1 次')).not.toBeInTheDocument()
  })

  it('renders canceled meetings when 已取消 is selected', async () => {
    renderList()
    await fireEvent.click(await screen.findByRole('button', { name: '高级筛选' }))
    await fireEvent.update(screen.getByLabelText('会议状态'), 'canceled')

    expect(screen.getByText('当前显示 1 场会议。')).toBeVisible()
    expect(screen.getByText('已取消的评审')).toBeVisible()
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
