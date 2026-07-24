import { fireEvent, render, screen } from '@testing-library/vue'
import { beforeEach, expect, it, vi } from 'vitest'

import PluginActionPanel from '../components/PluginActionPanel.vue'
import AiTasksView from '../views/AiTasksView.vue'

const { apiMock } = vi.hoisted(() => ({ apiMock: vi.fn() }))
vi.mock('../api/client', () => ({ api: apiMock }))

beforeEach(() => apiMock.mockReset())

it('submits a meeting-summary job once instead of running a draft inline', async () => {
  apiMock.mockResolvedValueOnce([
    {
      action_id: 'ai-work-assistant.meeting_summary',
      label: '生成会议纪要',
      description: '生成草稿',
      input_schema: { type: 'object' },
      target_types: ['meeting'],
    },
  ]).mockResolvedValueOnce({ id: 'job-1', status: 'queued' })

  render(PluginActionPanel, { props: { targetType: 'meeting', targetId: 'meeting-1' } })
  await fireEvent.click(await screen.findByRole('button', { name: '生成会议纪要' }))

  expect(apiMock).toHaveBeenCalledWith('/api/plugin-jobs', expect.objectContaining({
    method: 'POST',
    body: JSON.stringify({
      action_id: 'ai-work-assistant.meeting_summary',
      target_type: 'meeting',
      target_id: 'meeting-1',
      input: {},
    }),
  }))
  expect(screen.getByText('任务已加入 AI 任务中心')).toBeInTheDocument()
})

it('applies a succeeded meeting-summary draft only after the user confirms', async () => {
  apiMock.mockResolvedValueOnce({
    items: [{
      id: 'job-1', action_id: 'ai-work-assistant.meeting_summary', target_type: 'meeting', target_id: 'meeting-1',
      status: 'succeeded', result: { markdown: '# AI 草稿', model: 'test-model' }, created_at: '2026-07-24T00:00:00Z',
      started_at: null, finished_at: '2026-07-24T00:01:00Z', error_message: null, applied_at: null,
    }],
  }).mockResolvedValueOnce({ id: 'meeting-1', version: 3 }).mockResolvedValueOnce({ summary_markdown: '# 已确认纪要' })

  render(AiTasksView, { global: { stubs: { RouterLink: { template: '<a><slot /></a>' } } } })
  await fireEvent.update(await screen.findByLabelText('编辑会议纪要草稿'), '# 已确认纪要')
  await fireEvent.click(screen.getByRole('button', { name: '应用到会议纪要' }))

  expect(apiMock).toHaveBeenCalledWith('/api/plugin-jobs/job-1/apply', expect.objectContaining({
    method: 'POST', body: JSON.stringify({ edited_markdown: '# 已确认纪要', expected_version: 3 }),
  }))
})

it('applies a confirmed project-progress draft as a project update', async () => {
  apiMock.mockResolvedValueOnce({
    items: [{
      id: 'job-2', action_id: 'ai-work-assistant.project_progress', target_type: 'project', target_id: 'project-1',
      status: 'succeeded', result: { markdown: '# AI 进展' }, created_at: '2026-07-24T00:00:00Z',
      started_at: null, finished_at: '2026-07-24T00:01:00Z', error_message: null, applied_at: null,
    }],
  }).mockResolvedValueOnce({ content_markdown: '# 已确认进展' })

  render(AiTasksView, { global: { stubs: { RouterLink: { template: '<a><slot /></a>' } } } })
  await fireEvent.update(await screen.findByLabelText('编辑项目进展草稿'), '# 已确认进展')
  await fireEvent.click(screen.getByRole('button', { name: '发布项目进展' }))

  expect(apiMock).toHaveBeenCalledWith('/api/plugin-jobs/job-2/apply', expect.objectContaining({
    method: 'POST', body: JSON.stringify({ edited_markdown: '# 已确认进展' }),
  }))
})
