import { fireEvent, render, screen } from '@testing-library/vue'
import { beforeEach, expect, it, vi } from 'vitest'

import AiTasksView from '../views/AiTasksView.vue'

const { apiMock } = vi.hoisted(() => ({ apiMock: vi.fn() }))
vi.mock('../api/client', () => ({ api: apiMock }))

beforeEach(() => apiMock.mockReset())

it('keeps succeeded work as a recovery link back to its meeting context', async () => {
  apiMock.mockResolvedValueOnce({
    items: [{
      id: 'job-1', action_id: 'ai-work-assistant.meeting_summary', target_type: 'meeting', target_id: 'meeting-1',
      status: 'succeeded', result: { markdown: '# AI 草稿', model: 'test-model' }, created_at: '2026-07-24T00:00:00Z',
      started_at: null, finished_at: '2026-07-24T00:01:00Z', error_message: null, applied_at: null,
    }],
  })

  render(AiTasksView, { global: { stubs: { RouterLink: { props: ['to'], template: '<a :href="to"><slot /></a>' } } } })
  const link = await screen.findByRole('link', { name: '回到会议' })
  const status = await screen.findByText('已生成')

  expect(link).toHaveAttribute('href', '/meetings/meeting-1')
  expect(status).toHaveClass('status-pill', 'ai-task-status')
  expect(status).toHaveAttribute('data-status', 'ready')
  expect(screen.queryByRole('button', { name: '应用到会议纪要' })).not.toBeInTheDocument()
})

it('keeps base task errors when no task extension is registered', async () => {
  apiMock.mockResolvedValueOnce({
    items: [{
      id: 'job-2', plugin_id: 'unregistered-plugin', action_id: 'ai-work-assistant.project_progress', target_type: 'project', target_id: 'project-1',
      status: 'failed', result: null, created_at: '2026-07-26T00:00:00Z', started_at: null, finished_at: '2026-07-26T00:00:01Z',
      error_message: 'AI 服务额度不足；请充值或更换有可用额度的 API Key。',
      error_detail: 'HTTP 402 · {"error":{"message":"Insufficient Balance"}}',
      applied_at: null,
    }],
  })

  render(AiTasksView, { global: { stubs: { RouterLink: { props: ['to'], template: '<a :href="to"><slot /></a>' } } } })
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
  apiMock.mockResolvedValueOnce({
    items: [{
      id: 'job-3', action_id: 'ai-work-assistant.agenda_notes', target_type: 'agenda_item', target_id: 'agenda-1',
      meeting_id: 'meeting-3', status: 'failed', result: null, created_at: '2026-08-02T00:00:00Z',
      started_at: null, finished_at: '2026-08-02T00:00:01Z', error_message: '模型不可用', applied_at: null,
    }],
  })

  render(AiTasksView, { global: { stubs: { RouterLink: { props: ['to'], template: '<a :href="to"><slot /></a>' } } } })

  const link = await screen.findByRole('link', { name: '回到会议' })
  expect(link).toHaveAttribute('href', '/meetings/meeting-3')
})
