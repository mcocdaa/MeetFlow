import { fireEvent, screen, waitFor } from '@testing-library/vue'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { nextTick } from 'vue'

import AiTasksView from '../views/AiTasksView.vue'
import { formatDateTime } from '../utils/time'
import { renderWithProviders } from './helpers'

const { apiMock } = vi.hoisted(() => ({ apiMock: vi.fn() }))
vi.mock('../api/client', () => ({ api: apiMock }))

const RouterLinkStub = { props: ['to'], template: '<a :href="to"><slot /></a>' }

const lin = { id: 'u1', username: 'lin', display_name: '林宇' }
const project = { id: 'p1', name: 'MeetFlow', slug: 'meetflow', memberships: [{ role: 'member', user: lin }] }

function jobFixture(overrides: Record<string, unknown> = {}) {
  return {
    id: 'job-1',
    plugin_id: 'ai-work-assistant',
    action_id: 'ai-work-assistant.meeting_summary',
    target_type: 'meeting',
    target_id: 'meeting-1',
    status: 'succeeded',
    result: { markdown: '# AI 草稿', model: 'test-model' },
    error_code: null,
    error_message: null,
    error_detail: null,
    rerun_of_id: null,
    applied_by: null,
    applied_at: null,
    dismissed_by: null,
    dismissed_at: null,
    created_at: '2026-07-24T00:00:00Z',
    started_at: null,
    finished_at: '2026-07-24T00:01:00Z',
    ...overrides,
  }
}

function mockJobs(items: unknown[]) {
  apiMock.mockImplementation((path: string) => {
    if (path === '/api/projects') return Promise.resolve([project])
    if (path.startsWith('/api/plugin-jobs?')) return Promise.resolve({ items })
    return Promise.resolve(undefined)
  })
}

function renderView() {
  return renderWithProviders(AiTasksView, { global: { stubs: { RouterLink: RouterLinkStub } } })
}

function jobListCalls() {
  return apiMock.mock.calls
    .map(([path]) => String(path))
    .filter((path) => path.startsWith('/api/plugin-jobs?'))
}

beforeEach(() => {
  apiMock.mockReset()
})

afterEach(() => {
  vi.useRealTimers()
})

it('keeps succeeded work as a recovery link back to its meeting context', async () => {
  mockJobs([jobFixture()])

  renderView()
  const link = await screen.findByRole('link', { name: '回到会议' })
  const status = await screen.findByText('已生成')
  const statusPill = status.closest('.n-tag')

  expect(link).toHaveAttribute('href', '/meetings/meeting-1')
  expect(statusPill).toHaveClass('status-pill', 'ai-task-status')
  expect(statusPill).toHaveAttribute('data-status', 'succeeded')
  expect(screen.queryByRole('button', { name: '应用到会议纪要' })).not.toBeInTheDocument()
})

it('keeps base task errors when no task extension is registered', async () => {
  mockJobs([jobFixture({
    id: 'job-2',
    plugin_id: 'unregistered-plugin',
    action_id: 'ai-work-assistant.project_progress',
    target_type: 'project',
    target_id: 'project-1',
    status: 'failed',
    result: null,
    error_message: 'AI 服务额度不足；请充值或更换有可用额度的 API Key。',
    error_detail: 'HTTP 402 · {"error":{"message":"Insufficient Balance"}}',
    finished_at: '2026-07-26T00:00:01Z',
  })])

  renderView()
  expect(await screen.findByText('AI 服务额度不足；请充值或更换有可用额度的 API Key。')).toBeInTheDocument()
  expect(screen.getByText('unregistered-plugin · ai-work-assistant.project_progress')).toBeInTheDocument()
  const detail = await screen.findByText(/Insufficient Balance/)
  const disclosure = detail.closest('details')

  expect(disclosure).not.toBeNull()
  expect(disclosure?.open).toBe(false)
  await fireEvent.click(screen.getByText('查看技术详情'))
  expect(disclosure?.open).toBe(true)
})

it('returns agenda work to its owning meeting from the task history', async () => {
  mockJobs([jobFixture({
    id: 'job-3',
    action_id: 'ai-work-assistant.agenda_notes',
    target_type: 'agenda_item',
    target_id: 'agenda-1',
    meeting_id: 'meeting-3',
    status: 'failed',
    result: null,
    error_message: '模型不可用',
  })])

  renderView()

  const link = await screen.findByRole('link', { name: '回到会议' })
  expect(link).toHaveAttribute('href', '/meetings/meeting-3')
})

it('dismisses a terminal unapplied job after confirming in the popconfirm', async () => {
  mockJobs([jobFixture()])

  renderView()
  await screen.findByText('已生成')
  await fireEvent.click(screen.getByRole('button', { name: '丢弃' }))

  expect(await screen.findByText('确定丢弃这份 AI 结果吗？丢弃后不会再出现在进行中列表。')).toBeVisible()
  await fireEvent.click(screen.getByRole('button', { name: '确认' }))

  await waitFor(() => expect(apiMock).toHaveBeenCalledWith('/api/plugin-jobs/job-1/dismiss', { method: 'POST' }))
})

it('shows the backend dismiss conflict message verbatim', async () => {
  const conflict = Object.assign(new Error('当前 AI 草稿无法丢弃'), {
    status: 409,
    code: 'plugin_job_not_dismissible',
  })
  apiMock.mockImplementation((path: string) => {
    if (path === '/api/projects') return Promise.resolve([project])
    if (path.startsWith('/api/plugin-jobs?')) return Promise.resolve({ items: [jobFixture()] })
    if (path.endsWith('/dismiss')) return Promise.reject(conflict)
    return Promise.resolve(undefined)
  })

  renderView()
  await screen.findByText('已生成')
  await fireEvent.click(screen.getByRole('button', { name: '丢弃' }))
  await fireEvent.click(await screen.findByRole('button', { name: '确认' }))

  expect(await screen.findByText('当前 AI 草稿无法丢弃')).toBeInTheDocument()
})

it('renders error_code, rerun source, actor, and timestamps in the card metadata', async () => {
  mockJobs([jobFixture({
    id: 'job-9',
    status: 'failed',
    error_code: 'quota_exceeded',
    rerun_of_id: 'job-0',
    applied_by: 'u1',
    applied_at: '2026-07-24T02:00:00Z',
    dismissed_by: 'u1',
    dismissed_at: '2026-07-24T03:00:00Z',
    finished_at: '2026-07-24T03:00:00Z',
  })])

  renderView()

  expect(await screen.findByText('错误码：quota_exceeded')).toBeInTheDocument()
  expect(screen.getByText('重跑自任务 #job-0')).toBeInTheDocument()
  expect(screen.getByText('应用人：林宇')).toBeInTheDocument()
  expect(screen.getByText(`应用时间：${formatDateTime('2026-07-24T02:00:00Z')}`)).toBeInTheDocument()
  expect(screen.getByText('丢弃人：林宇')).toBeInTheDocument()
  expect(screen.getByText(`丢弃时间：${formatDateTime('2026-07-24T03:00:00Z')}`)).toBeInTheDocument()
  expect(screen.getByText('已丢弃结果')).toBeInTheDocument()
})

it('explains that results are applied from the originating editor', async () => {
  mockJobs([jobFixture()])

  renderView()

  expect(await screen.findByText('在发起页面应用此结果')).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: /应用到/ })).not.toBeInTheDocument()
})

it('does not offer dismiss on applied or dismissed jobs', async () => {
  mockJobs([
    jobFixture({ id: 'job-applied', applied_by: 'u1', applied_at: '2026-07-24T02:00:00Z' }),
    jobFixture({ id: 'job-dismissed', dismissed_by: 'u1', dismissed_at: '2026-07-24T03:00:00Z' }),
  ])

  renderView()

  expect((await screen.findAllByText('已应用')).length).toBeGreaterThan(0)
  expect(screen.getByText('已丢弃')).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: '丢弃' })).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: /应用/ })).not.toBeInTheDocument()
})

it('defaults to active jobs and reloads with include_history when switching to all', async () => {
  mockJobs([])

  renderView()
  await waitFor(() => expect(jobListCalls()).toContain('/api/plugin-jobs?include_history=false'))

  await fireEvent.click(screen.getByRole('radio', { name: '全部' }))

  await waitFor(() => expect(jobListCalls()).toContain('/api/plugin-jobs?include_history=true'))
})

it('keeps polling while a job is queued', async () => {
  vi.useFakeTimers()
  mockJobs([jobFixture({ status: 'queued', result: null, finished_at: null })])

  renderView()
  await vi.advanceTimersByTimeAsync(0)
  await nextTick()
  expect(jobListCalls()).toHaveLength(1)

  await vi.advanceTimersByTimeAsync(3_000)
  expect(jobListCalls()).toHaveLength(2)
})
